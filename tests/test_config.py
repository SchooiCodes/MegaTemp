import pytest

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

class TestConfigProfiles:
	def test_set_profile(self, isolated_fs):
		from utilities.fs import set_config_profile, _config_path, read_config, write_default_config
		# Default: config.json
		assert _config_path().endswith("config.json")
		set_config_profile("testprof")
		assert "config-testprof.json" in _config_path()
		# Reset for other tests
		set_config_profile("")
		assert _config_path().endswith("config.json")

	def test_profile_separate_config(self, isolated_fs):
		from utilities.fs import set_config_profile, read_config, write_default_config
		from utilities.models import Config

		# Write default config (no profile)
		cfg = write_default_config()
		assert cfg is not None

		# Switch profile and verify no config exists yet
		set_config_profile("alt")
		result = read_config()
		assert result is None

		# Reset
		set_config_profile("")


# ======================================================================
# Config migration v2->v3 tests
# ======================================================================

class TestConfigMigrationV2:
	def test_migrate_v2_to_v3(self):
		from utilities.models import migrate_config
		raw = {
			"schemaVersion": 2,
			"executablePath": "/p",
			"jsonlExport": True,
			"mailTimeout": 90,
			"quiet": True,
		}
		migrated = migrate_config(raw)
		assert migrated["schemaVersion"] == 3
		assert migrated["webhookUrl"] == ""
		assert migrated["executablePath"] == "/p"
		assert migrated["jsonlExport"] is True
		assert migrated["quiet"] is True

	def test_migrate_v0_through_v3(self):
		from utilities.models import migrate_config
		raw = {"executablePath": "/test"}
		migrated = migrate_config(raw)
		assert migrated["schemaVersion"] == 3
		assert migrated["webhookUrl"] == ""
		assert migrated["quiet"] is False
		assert migrated["mailTimeout"] == 45
		assert migrated["jsonlExport"] is False


# ======================================================================
# Encryption tests
# ======================================================================

class TestConfigMailTimeout:
	def test_mail_timeout_from_config(self):
		from utilities.models import Config
		cfg = Config(mailTimeout=60)
		assert cfg.mailTimeout == 60

	def test_mail_timeout_default(self):
		from utilities.models import Config
		cfg = Config()
		assert cfg.mailTimeout == 45

class TestConfigDefaults:
	def test_config_default_webhook_url(self):
		from utilities.models import Config
		c = Config()
		assert c.webhookUrl == ""

	def test_config_default_encryption_password(self):
		from utilities.models import Config
		c = Config()
		assert c.encryptionPassword == ""

