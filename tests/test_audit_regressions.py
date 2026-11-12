"""Regression tests for the 2026-11-11 audit findings (B1-B36)."""

import json
import os
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from utilities.models import Credentials

MAIN_PY = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "main.py"))


class TestConsoleShim:
	def test_ascii_env_forces_ascii(self):
		env = dict(os.environ, MEGATEMP_ASCII="1")
		result = subprocess.run(
			[
				sys.executable,
				"-c",
				"from utilities import console; print(console.init())",
			],
			capture_output=True,
			text=True,
			env=env,
			timeout=30,
		)
		assert result.returncode == 0
		assert "False" in result.stdout


class TestHashcashTimeout:
	def test_timeout_returns_bounded(self, monkeypatch):
		from utilities import hashcash

		monkeypatch.setattr(hashcash, "threshold_from_easiness", lambda _e: 0)
		start = time.monotonic()
		token = hashcash.mega_b64encode(b"x" * 48)
		with pytest.raises(TimeoutError):
			hashcash.gencash(token, 192, timeout_seconds=0.05, max_workers=2)
		assert time.monotonic() - start < 3.0


class TestCredentialHelpers:
	def test_unknown_config_key_tolerated(self, isolated_fs):
		from utilities.fs import merge_config, read_config

		# Unknown keys must be ignored, not crash the loader.
		merge_config({"unknownKey": 1})
		cfg = read_config()
		assert cfg is not None
		assert cfg.emailProvider == "mailtm"

	def test_find_update_delete_encrypted_roundtrip(self, isolated_fs):
		from utilities import fs

		fs._encryption_password_cache = ""
		fs.merge_config({"encryptionPassword": "pw"})
		creds = Credentials(email="user+tag@example.com", password="old")
		fs.save_credentials(creds, "", encryption_password="pw")

		path = fs.find_credential_path("user+tag@example.com")
		assert path is not None and path.endswith(".json")

		assert fs.update_credential("user+tag@example.com", password="new") is True
		data, encrypted = fs.load_credential_file(path, "pw")
		assert encrypted is True
		assert data["password"] == "new"

		assert fs.delete_credential("user+tag@example.com") is True
		assert fs.find_credential_path("user+tag@example.com") is None


class TestExtractDecrypts:
	def test_encrypted_credential_exported_plaintext(self, isolated_fs):
		from utilities import fs
		from services.extract import extract_credentials

		fs._encryption_password_cache = ""
		fs.merge_config({"encryptionPassword": "pw"})
		fs.save_credentials(
			Credentials(email="user@example.com", password="secret"),
			"",
			encryption_password="pw",
		)
		extract_credentials()
		text = open("credentials.txt", encoding="utf-8").read()
		assert "user@example.com#secret" in text
		assert "ENC:" not in text


class TestProviderSessions:
	def test_guerrilla_password_and_token(self, monkeypatch):
		import asyncio

		from utilities import guerrilla

		monkeypatch.setattr(
			guerrilla,
			"_gm_call",
			lambda _params: {
				"email_addr": "abc@guerrillamail.test",
				"sid_token": "sid-1",
			},
		)
		prov = guerrilla.GuerrillaMailProvider()
		creds = asyncio.run(prov.create_account())
		assert creds.password and len(creds.password) >= 20
		assert creds.emailPassword == "sid-1"

		mailbox = asyncio.run(prov.login(creds))
		assert mailbox.token == "sid-1"
		assert mailbox.address == "abc@guerrillamail.test"

	def test_mailtm_login_and_get_message(self, monkeypatch):
		import asyncio

		from utilities import mailtm_provider

		class FakeAccount:
			def __init__(self, id, address, password):
				self.id_ = id
				self.address = address
				self.password = password

			def get_messages(self):
				return [
					SimpleNamespace(
						id_="m1",
						from_={"address": "mega@example.com"},
						subject="Confirm",
						text="click here",
						html="<p>click here</p>",
					)
				]

		monkeypatch.setattr(mailtm_provider.pymailtm, "Account", FakeAccount)
		prov = mailtm_provider.MailTmProvider()
		creds = Credentials(email="abc@mail.tm", emailPassword="mailpw", id="acct-1")
		mailbox = asyncio.run(prov.login(creds))
		assert mailbox.address == "abc@mail.tm"
		assert mailbox.token == "mailpw"

		message = asyncio.run(prov.get_message(mailbox))
		assert message["mail_id"] == "m1"
		assert message["mail_body"] == "click here"


class TestMailCacheKey:
	def test_different_identities_have_different_keys(self):
		from utilities.web import _mail_cache_key

		a = _mail_cache_key(Credentials(email="a@x", emailPassword="p1"))
		b = _mail_cache_key(Credentials(email="a@x", emailPassword="p2"))
		c = _mail_cache_key(Credentials(email="b@x", emailPassword="p1"))
		assert len({a, b, c}) == 3


class TestFastBrowserFreeCommands:
	def test_version_does_not_create_config(self, tmp_path):
		start = time.monotonic()
		result = subprocess.run(
			[sys.executable, MAIN_PY, "--version"],
			capture_output=True,
			text=True,
			cwd=tmp_path,
			timeout=10,
		)
		assert result.returncode == 0
		assert "v1.6.0" in result.stdout
		assert not (tmp_path / "config.json").exists()
		assert time.monotonic() - start < 2.0

	def test_health_json_does_not_create_config(self, tmp_path):
		start = time.monotonic()
		result = subprocess.run(
			[sys.executable, MAIN_PY, "--health", "--json"],
			capture_output=True,
			text=True,
			cwd=tmp_path,
			timeout=10,
		)
		assert result.returncode == 0
		data = json.loads(result.stdout[result.stdout.index("{") :])
		assert "error" in data or "accounts" in data
		assert not (tmp_path / "config.json").exists()
		assert time.monotonic() - start < 2.0


class TestRemainingAuditEdges:
	def test_find_credential_path_accounts_txt(self, isolated_fs):
		from utilities.fs import find_credential_path, save_credentials

		save_credentials(
			Credentials(email="txt@example.com", password="pw"),
			"{email}#{password}",
		)
		path = find_credential_path("txt@example.com")
		assert path is not None
		assert path.endswith("accounts.txt")

	def test_patch_mega_is_idempotent(self):
		# Run in a subprocess so patching does not leak into other tests.
		code = (
			"import utilities.compat  # restores asyncio.coroutine\n"
			"from utilities.mega_patch import patch_mega\n"
			"import mega\n"
			"patch_mega()\n"
			"first = mega.Mega._api_request\n"
			"patch_mega()\n"
			"assert mega.Mega._api_request is first\n"
			"print('ok')\n"
		)
		result = subprocess.run(
			[sys.executable, "-c", code],
			capture_output=True,
			text=True,
			cwd=os.path.dirname(MAIN_PY),
			timeout=60,
		)
		assert result.returncode == 0, result.stderr
		assert "ok" in result.stdout
