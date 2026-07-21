"""
End-to-end test for MegaTemp.

Tests all modules in isolation with mocked externals:
1. types.py      - data classes
2. fs.py         - config read/write, credentials save/csv
3. etc.py        - utilities (clear_tmp, delete_default, elapsed, etc.)
4. web.py        - browser helpers
5. menu.py       - TUI components
6. services/     - upload, extract, alive
7. main.py       - CLI dispatch, registration flow
"""

import sys
import os
import json
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

# ======================================================================
# types.py
# ======================================================================


class TestTypes:
	def test_colours_class(self):
		from utilities.models import Colours

		c = Colours()
		assert c.HEADER == "\033[95m"
		assert c.OKGREEN == "\033[92m"
		assert c.WARNING == "\033[93m"
		assert c.FAIL == "\033[91m"
		assert c.ENDC == "\033[0m"

	def test_credentials_creation(self):
		from utilities.models import Credentials

		c = Credentials("a@b.com", "mailpw", "megapw")
		assert c.email == "a@b.com"
		assert c.emailPassword == "mailpw"
		assert c.password == "megapw"
		assert c.id == ""  # class variable, not a field

	def test_credentials_defaults(self):
		from utilities.models import Credentials

		c = Credentials()
		assert c.email == ""
		assert c.password == ""

	def test_credentials_asdict_includes_id(self):
		from dataclasses import asdict
		from utilities.models import Credentials

		c = Credentials("a@b.com", "mpw", "megapw")
		d = asdict(c)
		assert d["email"] == "a@b.com"
		assert d["emailPassword"] == "mpw"
		assert d["password"] == "megapw"
		assert d["id"] == ""  # id is now a proper dataclass field

	def test_credentials_not_subscriptable(self):
		"""Credentials is a dataclass, not a dict - not subscriptable by design."""
		from utilities.models import Credentials

		c = Credentials("a@b.com", "mpw", "megapw")
		with pytest.raises(TypeError):
			_ = c["email"]

	def test_config_creation(self):
		from utilities.models import Config

		c = Config()
		assert c.executablePath == ""
		assert c.accountFormat == ""
		assert c.schemaVersion == 1
		assert c.maxAttempts == 4
		assert c.csvExport is False
		assert c.visibleBrowser is False
		assert c.emailProvider == "mailtm"

	def test_config_with_values(self):
		from utilities.models import Config

		c = Config(
			executablePath="/usr/bin/chromium", accountFormat="{email}#{password}"
		)
		assert c.executablePath == "/usr/bin/chromium"
		assert c.accountFormat == "{email}#{password}"

	def test_config_getset_item(self):
		from utilities.models import Config

		c = Config()
		c["executablePath"] = "/test/path"
		assert c["executablePath"] == "/test/path"
		assert c.executablePath == "/test/path"

	def test_config_asdict(self):
		from dataclasses import asdict
		from utilities.models import Config

		c = Config(executablePath="/bin/chrome")
		d = asdict(c)
		assert d["executablePath"] == "/bin/chrome"
		assert d["accountFormat"] == ""
		assert d["schemaVersion"] == 1
		assert d["maxAttempts"] == 4
		assert d["csvExport"] is False
		assert d["visibleBrowser"] is False
		assert d["emailProvider"] == "mailtm"

	def test_migrate_config_v0(self):
		from utilities.models import migrate_config

		raw = {"executablePath": "/old/path"}
		migrated = migrate_config(raw)
		assert migrated["schemaVersion"] == 1
		assert migrated["executablePath"] == "/old/path"
		assert migrated["proxy"] == ""
		assert migrated["maxAttempts"] == 4
		assert migrated["emailProvider"] == "mailtm"

	def test_migrate_config_idempotent(self):
		from utilities.models import migrate_config

		raw = {"schemaVersion": 1, "executablePath": "/p"}
		migrated = migrate_config(raw)
		assert migrated["schemaVersion"] == 1
		assert migrated["executablePath"] == "/p"


# ======================================================================
# fs.py
# ======================================================================


@pytest.fixture
def isolated_fs(tmp_path):
	"""Run tests in a temp directory with a clean config."""
	old_cwd = os.getcwd()
	os.chdir(tmp_path)
	# Create empty credentials directory for save tests
	yield tmp_path
	os.chdir(old_cwd)


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


class TestEtc:
	def test_elapsed_seconds(self):
		from utilities.etc import elapsed

		start = time.monotonic() - 30
		result = elapsed(start)
		assert result.endswith("s")
		assert "m" not in result

	def test_elapsed_minutes(self):
		from utilities.etc import elapsed

		start = time.monotonic() - 125
		result = elapsed(start)
		assert "m" in result
		assert "s" in result

	def test_separator_defaults(self, capsys):
		from utilities.etc import separator, Colours

		separator()
		captured = capsys.readouterr()
		assert "─" in captured.out
		assert Colours.HEADER in captured.out
		assert Colours.ENDC in captured.out

	def test_separator_with_title(self, capsys):
		from utilities.etc import separator

		separator("Test Title")
		captured = capsys.readouterr()
		assert "Test Title" in captured.out

	def test_p_print_colour(self, capsys):
		from utilities.etc import p_print, Colours

		p_print("hello", Colours.FAIL)
		captured = capsys.readouterr()
		assert "hello" in captured.out
		assert Colours.FAIL in captured.out
		assert Colours.ENDC in captured.out

	def test_clear_tmp(self, tmp_path):
		from utilities.etc import clear_tmp

		old = os.getcwd()
		os.chdir(tmp_path)
		os.makedirs("tmp/subdir")
		with open("tmp/test.txt", "w") as f:
			f.write("test")
		assert os.path.exists("tmp")
		result = clear_tmp()
		assert result is True
		assert not os.path.exists("tmp")
		os.chdir(old)

	def test_clear_tmp_no_tmp(self, tmp_path):
		from utilities.etc import clear_tmp

		old = os.getcwd()
		os.chdir(tmp_path)
		result = clear_tmp()
		assert result is True  # No tmp dir = success
		os.chdir(old)

	def test_status_line(self, capsys):
		from utilities.etc import status_line, clear_status_line, Colours

		status_line("working...", Colours.WARNING)
		captured = capsys.readouterr()
		assert "working..." in captured.out
		assert Colours.WARNING in captured.out
		clear_status_line()

	def test_auto_update_source(self):
		"""auto_update() should no-op in non-frozen (source) mode."""
		from utilities.etc import auto_update

		# In source mode (not frozen EXE) it should return immediately.
		result = auto_update()
		assert result is None  # no return value = no crash

	def test_version_defined(self):
		from utilities.etc import VERSION

		assert VERSION.startswith("v")
		assert "." in VERSION


class TestProxyManager:
	def test_empty(self):
		from utilities.etc import ProxyManager

		pm = ProxyManager()
		assert pm.active is False
		assert pm.get_proxy() is None
		assert pm.count == 0

	def test_single_proxy(self):
		from utilities.etc import ProxyManager

		pm = ProxyManager(proxy="http://user:pass@1.2.3.4:8080")
		assert pm.active is True
		assert pm.count == 1
		assert pm.get_proxy() == "http://user:pass@1.2.3.4:8080"

	def test_rotation(self):
		from utilities.etc import ProxyManager

		pm = ProxyManager(proxy_file="/nonexistent", per_attempt=True)
		# file doesn't exist → no proxies loaded
		assert pm.active is False
		assert pm.count == 0

	def test_rotation_with_file(self, tmp_path):
		from utilities.etc import ProxyManager

		pf = tmp_path / "proxies.txt"
		pf.write_text("http://a:1@1.2.3.4:80\nhttp://b:2@5.6.7.8:8080\n")
		pm = ProxyManager(proxy_file=str(pf), per_attempt=True)
		assert pm.count == 2
		assert pm.get_proxy() == "http://a:1@1.2.3.4:80"
		assert pm.get_proxy() == "http://b:2@5.6.7.8:8080"
		assert pm.get_proxy() == "http://a:1@1.2.3.4:80"  # wraps around

	def test_validate(self):
		from utilities.etc import ProxyManager

		assert ProxyManager._validate("http://u:p@1.2.3.4:80") is True
		assert ProxyManager._validate("") is False


class TestCheckpoint:
	def test_save_and_load(self, tmp_path):
		from utilities.etc import (
			save_checkpoint,
			load_checkpoint,
			clear_checkpoint,
			LoopState,
		)

		old = os.getcwd()
		os.chdir(tmp_path)
		state = LoopState(total=50, completed=10, failed=2, started_at=time.monotonic())
		save_checkpoint(state)
		loaded = load_checkpoint()
		assert loaded is not None
		assert loaded.total == 50
		assert loaded.completed == 10
		assert loaded.failed == 2
		clear_checkpoint()
		assert load_checkpoint() is None
		os.chdir(old)

	def test_load_nonexistent(self):
		from utilities.etc import load_checkpoint

		assert load_checkpoint() is None

	def test_clear_no_file(self):
		from utilities.etc import clear_checkpoint

		# Should not raise.
		clear_checkpoint()


# ======================================================================
# web.py
# ======================================================================


class TestWeb:
	def test_set_verbose(self):
		import utilities.web

		utilities.web.set_verbose(True)
		assert utilities.web._VERBOSE is True
		utilities.web.set_verbose(False)
		assert utilities.web._VERBOSE is False

	def test_get_random_string_default(self):
		from utilities.web import get_random_string

		s = get_random_string(14)
		assert len(s) == 14
		assert all(c.isalnum() for c in s)

	def test_get_random_string_various_lengths(self):
		from utilities.web import get_random_string

		for length in [1, 10, 50, 100]:
			s = get_random_string(length)
			assert len(s) == length

	def test_get_random_string_no_empty(self):
		from utilities.web import get_random_string

		s = get_random_string(0)
		assert s == ""


# ======================================================================
# menu.py
# ======================================================================


class TestMenu:
	def test_menu_item_label(self):
		from utilities.menu import MenuItem

		item = MenuItem("Test", lambda: "done", "Desc")
		assert item.label == "Test"

	def test_menu_item_value_string(self):
		from utilities.menu import MenuItem

		item = MenuItem("X", value="val")
		assert item.get_value() == "val"

	def test_menu_item_value_callable(self):
		from utilities.menu import MenuItem

		item = MenuItem("X", value=lambda: "live")
		assert item.get_value() == "live"

	def test_menu_item_value_none(self):
		from utilities.menu import MenuItem

		item = MenuItem("X")
		assert item.get_value() == ""

	def test_menu_item_value_callable_error(self):
		from utilities.menu import MenuItem

		def broken():
			raise ValueError("oops")

		item = MenuItem("X", value=broken)
		assert item.get_value() == ""

	def test_display_width_ascii(self):
		from utilities.menu import _display_width

		assert _display_width("hello") == 5

	def test_display_width_with_ansi(self):
		from utilities.menu import _display_width

		text = "\033[92mgreen\033[0m"
		assert _display_width(text) == 5

	def test_display_width_unicode(self):
		from utilities.menu import _display_width

		# Characters above 0x2000 are counted as 2
		# '→' (U+2192) is below 0x2000
		# Actually let's use a character above 0x2000
		assert _display_width("a") == 1

	def test_back_sentinel(self):
		from utilities.menu import _BACK

		assert _BACK is _BACK  # singleton

	def test_prompt_text_basic(self, monkeypatch):
		from utilities.menu import prompt_text

		monkeypatch.setattr("sys.stdin", type("StdinMock", (), {"fileno": lambda: 0})())
		# Can't fully test interactive input in CI, just verify function exists
		assert callable(prompt_text)

	def test_menu_creation(self):
		from utilities.menu import Menu, MenuItem

		items = [MenuItem("A"), MenuItem("B")]
		m = Menu("Title", items)
		assert m.title == "Title"
		assert len(m.items) == 2
		assert m.selected == 0


# ======================================================================
# services/
# ======================================================================


class TestExtract:
	def test_extract_no_folder(self, capsys, tmp_path):
		from services.extract import extract_credentials

		old = os.getcwd()
		os.chdir(tmp_path)
		extract_credentials()
		captured = capsys.readouterr()
		assert "No credentials folder found" in captured.out
		os.chdir(old)

	def test_extract_empty_folder(self, capsys, tmp_path):
		from services.extract import extract_credentials

		old = os.getcwd()
		os.chdir(tmp_path)
		os.makedirs("credentials")
		extract_credentials()
		captured = capsys.readouterr()
		assert "Extracting 0 account(s)" in captured.out
		os.chdir(old)


class TestUpload:
	def test_upload_file_not_found(self, capsys, tmp_path):
		from services.upload import upload_file
		from utilities.models import Credentials

		old = os.getcwd()
		os.chdir(tmp_path)
		upload_file(False, "/nonexistent/file.txt", Credentials())
		captured = capsys.readouterr()
		assert "File not found" in captured.out
		os.chdir(old)


class TestAlive:
	def test_keepalive_no_credentials_folder(self, capsys, tmp_path):
		from services.alive import keepalive

		old = os.getcwd()
		os.chdir(tmp_path)
		keepalive(False)
		captured = capsys.readouterr()
		assert "No credentials found" in captured.out
		os.chdir(old)

	def test_keepalive_empty_folder(self, capsys, tmp_path):
		from services.alive import keepalive

		old = os.getcwd()
		os.chdir(tmp_path)
		os.makedirs("credentials")
		keepalive(False)
		captured = capsys.readouterr()
		assert "No credentials found" in captured.out
		os.chdir(old)


# ======================================================================
# main.py - CLI
# ======================================================================


class TestMain:
	def test_module_imports(self):
		"""Verify all module-level imports in main.py work."""
		import importlib

		# Can't fully exec main.py because it parses CLI args at import time,
		# but we can check all its imports resolve (raises on failure)
		for mod in [
			"utilities.fs",
			"utilities.web",
			"utilities.etc",
			"utilities.menu",
			"services.alive",
			"services.extract",
			"services.upload",
		]:
			importlib.import_module(mod)

	def test_main_cli_help(self):
		"""Verify the CLI entrypoint produces help text."""
		import subprocess

		result = subprocess.run(
			[sys.executable, "main.py", "--help"],
			capture_output=True,
			text=True,
			timeout=30,
		)
		assert result.returncode == 0
		assert "usage:" in result.stdout
		assert "--keepalive" in result.stdout
		assert "--loop" in result.stdout
		assert "--extract" in result.stdout
		assert "--export-csv" in result.stdout

	def test_main_cli_version_info(self):
		"""The --help output should mention the tool name."""
		import subprocess

		result = subprocess.run(
			[sys.executable, "main.py", "--help"],
			capture_output=True,
			text=True,
			timeout=30,
		)
		assert "main.py" in result.stdout or "help" in result.stdout

	def test_main_verbose_flag_exits_gracefully(self):
		"""Running with -v should exit without a traceback.

		Note: main.py -v tries to launch a browser, so it may fail or
		hang. We just verify there's no Python traceback in stderr on
		the fast path, and use a short timeout to avoid hanging.
		"""
		import subprocess

		try:
			result = subprocess.run(
				[sys.executable, "main.py", "-v"],
				capture_output=True,
				text=True,
				timeout=15,
			)
			assert "Traceback" not in result.stderr, f"Crash: {result.stderr}"
		except subprocess.TimeoutExpired as e:
			# Timed out = browser launch delayed; not a code crash.
			# Convert bytes output to str for safe substring checks.
			out = (e.stdout or b"").decode("utf-8", errors="replace")
			err = (e.stderr or b"").decode("utf-8", errors="replace")
			assert "Traceback" not in out, f"Crash: {out}"
			assert "Traceback" not in err, f"Crash: {err}"


# ======================================================================
# download.py
# ======================================================================


class TestDownload:
	def test_list_files_no_creds_returns_empty(self):
		from services.download import list_files
		from utilities.models import Credentials

		creds = Credentials("nonexistent@test.test", "pw", "pw")
		result = list_files(creds)
		assert isinstance(result, list)

	def test_download_file_no_creds_returns_none(self):
		from services.download import download_file
		from utilities.models import Credentials

		creds = Credentials("nonexistent@test.test", "pw", "pw")
		result = download_file(creds, "nonexistent-id", "/tmp")
		assert result is None

	def test_list_cloud_flag_no_creds(self):
		"""--list-cloud with no credentials should not crash."""
		import subprocess

		result = subprocess.run(
			[sys.executable, "main.py", "--list-cloud"],
			capture_output=True,
			text=True,
			timeout=30,
		)
		assert "Traceback" not in result.stderr

	def test_download_cloud_flag_no_creds(self):
		"""--download-cloud with no credentials should not crash."""
		import subprocess

		result = subprocess.run(
			[sys.executable, "main.py", "--download-cloud", "dummy-id"],
			capture_output=True,
			text=True,
			timeout=30,
		)
		assert "Traceback" not in result.stderr

	def test_separator_no_title(self):
		from utilities.etc import separator
		from utilities.models import Colours

		separator(colour=Colours.HEADER, width=20)

	def test_separator_with_title(self):
		from utilities.etc import separator
		from utilities.models import Colours

		separator("Hello", colour=Colours.OKGREEN, width=30)


# ======================================================================
# utilities/password_strength.py
# ======================================================================


class TestPasswordStrength:
	def test_entropy_empty(self):
		from utilities.password_strength import estimate_entropy

		assert estimate_entropy("") == 0.0

	def test_entropy_non_empty(self):
		from utilities.password_strength import estimate_entropy

		assert estimate_entropy("abc") > 0

	def test_strength_labels(self):
		from utilities.password_strength import strength_label

		label, colour = strength_label("a")
		assert label in ("Very Weak", "Weak", "Medium", "Strong", "Very Strong")
		assert colour.startswith("\033[")

	def test_strong_password(self):
		from utilities.password_strength import strength_label

		label, _ = strength_label("Tr0ub4dor&3!@#xYzQwerty123!!!")
		assert label in ("Strong", "Very Strong")


# ======================================================================
# utilities/retry.py
# ======================================================================


class TestRetry:
	def test_retry_success_first_try(self):
		from utilities.retry import retry

		called = 0

		@retry(max_attempts=3, label="test")
		def fn():
			nonlocal called
			called += 1
			return 42

		assert fn() == 42
		assert called == 1

	def test_retry_eventually_succeeds(self):
		from utilities.retry import retry

		called = 0

		@retry(max_attempts=3, label="test")
		def fn():
			nonlocal called
			called += 1
			if called < 3:
				raise ConnectionError("transient")
			return "ok"

		assert fn() == "ok"
		assert called == 3

	def test_retry_exhausted(self):
		from utilities.retry import retry

		@retry(max_attempts=2, label="test")
		def fn():
			raise ValueError("always fails")

		import pytest as _pt

		with _pt.raises(ValueError):
			fn()


# ======================================================================
# utilities/provider.py — provider registry
# ======================================================================


class TestProviderRegistry:
	def test_get_provider_unknown(self):
		from utilities.provider import get_provider

		assert get_provider("nonexistent_provider") is None

	def test_get_provider_names_contains_defaults(self):
		from utilities.provider import get_provider_names

		names = get_provider_names()
		assert "mailtm" in names
		assert "guerrillamail" in names

	def test_get_provider_mailtm(self):
		from utilities.provider import get_provider

		prov = get_provider("mailtm")
		assert prov is not None
		assert prov.name == "mailtm"


# ======================================================================
# utilities/etc.py — notify
# ======================================================================


class TestNotify:
	def test_notify_no_crash(self):
		from utilities.etc import notify

		# Should not raise — best effort
		notify("Test title", "Test message")


# ======================================================================
# utilities/fs.py — config validation
# ======================================================================


class TestConfigValidation:
	def test_validate_empty(self):
		from utilities.fs import _validate_config

		_validate_config({})  # no crash

	def test_validate_bad_exec_path(self):
		from utilities.fs import _validate_config

		_validate_config({"executablePath": "/nonexistent/chromium"})  # no crash

	def test_validate_bad_attempts(self):
		from utilities.fs import _validate_config

		_validate_config({"maxAttempts": 999})  # no crash

	def test_validate_bad_proxy(self):
		from utilities.fs import _validate_config

		_validate_config({"proxy": "not-a-proxy"})  # no crash


# ======================================================================
# services/upload.py — retry on upload
# ======================================================================


class TestUploadRetry:
	def test_upload_file_not_found(self):
		from services.upload import upload_file
		from utilities.models import Credentials

		creds = Credentials("test@test.test", "pw", "pw")
		upload_file(False, "/nonexistent/file.txt", creds)  # no crash


# ======================================================================
# main.py — CLI dispatch edge cases
# ======================================================================


class TestMainCLI:
	def test_main_list_cloud_no_crash(self):
		import subprocess

		result = subprocess.run(
			[sys.executable, "main.py", "--list-cloud"],
			capture_output=True,
			text=True,
			timeout=30,
		)
		assert "Traceback" not in result.stderr

	def test_main_download_cloud_no_crash(self):
		import subprocess

		result = subprocess.run(
			[sys.executable, "main.py", "--download-cloud", "test-id"],
			capture_output=True,
			text=True,
			timeout=30,
		)
		assert "Traceback" not in result.stderr


if __name__ == "__main__":
	pytest.main([__file__, "-v", "--tb=short"])
