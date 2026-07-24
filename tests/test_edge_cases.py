import pytest

class TestEdgeCases:
	def test_send_webhook_quiet_mode(self):
		from utilities.etc import send_webhook, set_quiet
		set_quiet(True)
		send_webhook("http://invalid.example.com/test", "test", {})  # no crash
		set_quiet(False)

	def test_encrypt_empty_password_fields(self):
		from utilities.fs import encrypt_credential
		data = {"email": "t@t.com", "password": "", "emailPassword": ""}
		result = encrypt_credential(dict(data), "key")
		assert result["password"] == ""
		assert result["emailPassword"] == ""

	def test_proxy_validate_edge_cases(self):
		from utilities.etc import ProxyManager
		assert ProxyManager._validate("") is False
		assert ProxyManager._validate("http://user:pass@host:port") is True
		assert ProxyManager._validate("a@b@c") is False

	def test_config_profile_write_read(self, isolated_fs):
		from utilities.fs import set_config_profile, read_config, write_default_config, merge_config, _config_path

		set_config_profile("testwrite")
		assert "config-testwrite.json" in _config_path()
		cfg = write_default_config()
		assert cfg is not None

		read_back = read_config()
		assert read_back is not None
		assert read_back.schemaVersion == 3

		merge_config({"maxAttempts": 10})
		read_back2 = read_config()
		assert read_back2 is not None
		assert read_back2.maxAttempts == 10

		set_config_profile("")

	def test_migrate_config_propagates_all_fields(self):
		from utilities.models import migrate_config
		raw = {"schemaVersion": 0, "executablePath": "/e"}
		m = migrate_config(raw)
		assert m["schemaVersion"] == 3
		assert m["quiet"] is False
		assert m["webhookUrl"] == ""
		assert m["encryptionPassword"] == ""

