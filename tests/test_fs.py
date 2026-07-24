import pytest
import os
import json

class TestFs:
	def test_write_default_config_creates_file(self, isolated_fs):
		from utilities.fs import write_default_config

		write_default_config()
		assert os.path.exists("config.json")
		with open("config.json") as f:
			data = json.load(f)
		assert "executablePath" in data
		assert "accountFormat" in data

	def test_read_config_nonexistent(self, isolated_fs):
		from utilities.fs import read_config

		cfg = read_config()
		assert cfg is None

	def test_read_config_after_write(self, isolated_fs):
		from utilities.fs import write_default_config, read_config

		write_default_config()
		cfg = read_config()
		assert cfg is not None
		assert isinstance(cfg.executablePath, str)

	def test_write_config_updates_file(self, isolated_fs):
		from utilities.fs import write_default_config, write_config, read_config

		write_default_config()
		cfg = read_config()
		write_config("executablePath", "/new/path", cfg)
		cfg2 = read_config()
		assert cfg2.executablePath == "/new/path"

	def test_concrete_read_config(self, isolated_fs):
		from utilities.fs import concrete_read_config, write_default_config

		write_default_config()
		cfg = concrete_read_config()
		assert cfg is not None

	def test_concrete_read_config_exits_on_failure(self, isolated_fs):
		from utilities.fs import concrete_read_config

		with pytest.raises(SystemExit):
			concrete_read_config()

	def test_save_credentials_json(self, isolated_fs):
		from utilities.models import Credentials
		from utilities.fs import save_credentials

		c = Credentials("user@test.domain", "mailpw", "megapw")
		save_credentials(c, "")
		assert os.path.isdir("credentials")
		files = os.listdir("credentials")
		json_files = [f for f in files if f.endswith(".json")]
		assert len(json_files) == 1
		with open(f"credentials/{json_files[0]}") as f:
			data = json.load(f)
		assert data["email"] == "user@test.domain"
		assert data["password"] == "megapw"
		assert data["emailPassword"] == "mailpw"

	def test_save_credentials_with_format(self, isolated_fs):
		from utilities.models import Credentials
		from utilities.fs import save_credentials

		c = Credentials("user@test.domain", "mailpw", "megapw")
		save_credentials(c, "{email}|{password}|{emailPassword}")
		assert os.path.isdir("credentials")
		with open("credentials/accounts.txt") as f:
			line = f.read().strip()
		assert line == "user@test.domain|megapw|mailpw"

	def test_save_credentials_csv(self, isolated_fs):
		from utilities.models import Credentials
		from utilities.fs import save_credentials_csv

		c = Credentials("csv@test.domain", "csvmailpw", "csvmegapw")
		save_credentials_csv(c)
		assert os.path.isdir("credentials")
		with open("credentials/accounts.csv") as f:
			content = f.read()
		assert "email,password,emailPassword" in content
		assert "csv@test.domain,csvmegapw,csvmailpw" in content

	def test_save_credentials_appends(self, isolated_fs):
		from utilities.models import Credentials
		from utilities.fs import save_credentials

		c1 = Credentials("user1@test.com", "mpw1", "megapw1")
		c2 = Credentials("user2@test.com", "mpw2", "megapw2")
		save_credentials(c1, "{email}")
		save_credentials(c2, "{email}")
		with open("credentials/accounts.txt") as f:
			lines = f.read().strip().split("\n")
		assert len(lines) == 2

	def test_save_credentials_safe_filename(self, isolated_fs):
		"""Email local parts with special chars should be sanitized."""
		from utilities.models import Credentials
		from utilities.fs import save_credentials

		c = Credentials("weird/name@test.com", "mpw", "megapw")
		save_credentials(c, "")
		json_files = [f for f in os.listdir("credentials") if f.endswith(".json")]
		assert len(json_files) == 1
		# The '/' in local part should be sanitized
		assert "weird_name" in json_files[0] or "weird" in json_files[0]

	def test_merge_config_adds_keys(self, isolated_fs):
		from utilities.fs import merge_config, write_default_config, read_config

		write_default_config()
		merge_config({"maxAttempts": 8, "visibleBrowser": True})
		cfg = read_config()
		assert cfg is not None
		assert cfg.maxAttempts == 8
		assert cfg.visibleBrowser is True

	def test_merge_config_preserves_existing(self, isolated_fs):
		from utilities.fs import merge_config, write_default_config, read_config

		write_default_config()
		cfg1 = read_config()
		old_path = cfg1.executablePath
		merge_config({"maxAttempts": 6})
		cfg2 = read_config()
		assert cfg2.executablePath == old_path

	def test_list_credentials_empty(self, isolated_fs):
		from utilities.fs import list_credentials

		assert list_credentials() == []

	def test_list_credentials_with_files(self, isolated_fs):
		from utilities.models import Credentials
		from utilities.fs import save_credentials, list_credentials

		c = Credentials("a@b.com", "mpw", "megapw")
		save_credentials(c, "")
		result = list_credentials()
		assert len(result) == 1
		fname, creds, _mtime = result[0]
		assert creds.email == "a@b.com"


# ======================================================================
# etc.py
# ======================================================================

class TestEncryption:
	def test_encrypt_decrypt_roundtrip(self):
		from utilities.fs import encrypt_credential, decrypt_credential
		data = {"email": "test@test.com", "password": "secret123", "emailPassword": "mailpw"}
		orig = dict(data)
		encrypted = encrypt_credential(dict(data), "mypassword")
		# password and emailPassword should be encrypted
		assert encrypted["password"] != orig["password"]
		assert encrypted["emailPassword"] != orig["emailPassword"]
		assert encrypted["email"] == orig["email"]  # email NOT encrypted
		# Decrypt back
		decrypted = decrypt_credential(encrypted, "mypassword")
		assert decrypted["password"] == orig["password"]
		assert decrypted["emailPassword"] == orig["emailPassword"]

	def test_encrypt_noop_without_password(self):
		from utilities.fs import encrypt_credential
		data = {"email": "t@t.com", "password": "pw"}
		result = encrypt_credential(dict(data), "")
		assert result == data

	def test_decrypt_noop_without_password(self):
		from utilities.fs import decrypt_credential
		data = {"email": "t@t.com", "password": "pw"}
		result = decrypt_credential(dict(data), "")
		assert result == data

	def test_wrong_password_fails_gracefully(self):
		from utilities.fs import encrypt_credential, decrypt_credential
		data = {"email": "t@t.com", "password": "secret"}
		encrypted = encrypt_credential(dict(data), "correct")
		# Wrong password should not crash but may produce garbage
		decrypted = decrypt_credential(encrypted, "wrong")
		assert decrypted["password"] != data["password"]

	def test_encrypted_save_and_list(self, isolated_fs):
		from utilities.models import Credentials
		from utilities.fs import save_credentials, list_credentials, encrypt_credential, decrypt_credential

		creds = Credentials("enc@test.com", "mailpw", "megapw")
		# Save with encryption password
		save_credentials(creds, "", "enc_key")

		# Read the raw file — should be encrypted
		import glob, json
		files = glob.glob("credentials/*.json")
		assert len(files) == 1
		with open(files[0]) as f:
			raw = json.load(f)
		assert raw["password"].startswith(("ENC:", "OBS:"))
		# list_credentials should auto-decrypt if config has the password
		# (without config it returns encrypted data — that's OK, no crash)

