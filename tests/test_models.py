import pytest
import os

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
		assert c.schemaVersion == 3
		assert c.maxAttempts == 4
		assert c.csvExport is False
		assert c.jsonlExport is False
		assert c.visibleBrowser is False
		assert c.emailProvider == "mailtm"
		assert c.mailTimeout == 45
		assert c.quiet is False
		assert c.webhookUrl == ""

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
		assert d["schemaVersion"] == 3
		assert d["maxAttempts"] == 4
		assert d["csvExport"] is False
		assert d["jsonlExport"] is False
		assert d["visibleBrowser"] is False
		assert d["emailProvider"] == "mailtm"
		assert d["mailTimeout"] == 45
		assert d["quiet"] is False
		assert d["webhookUrl"] == ""

	def test_migrate_config_v0(self):
		from utilities.models import migrate_config

		raw = {"executablePath": "/old/path"}
		migrated = migrate_config(raw)
		assert migrated["schemaVersion"] == 3
		assert migrated["executablePath"] == "/old/path"
		assert migrated["proxy"] == ""
		assert migrated["maxAttempts"] == 4
		assert migrated["emailProvider"] == "mailtm"
		assert migrated["jsonlExport"] is False
		assert migrated["mailTimeout"] == 45
		assert migrated["quiet"] is False
		assert migrated["webhookUrl"] == ""

	def test_migrate_config_idempotent(self):
		from utilities.models import migrate_config

		raw = {"schemaVersion": 2, "executablePath": "/p",
		       "jsonlExport": True, "mailTimeout": 60, "quiet": True}
		migrated = migrate_config(raw)
		assert migrated["schemaVersion"] == 3
		assert migrated["executablePath"] == "/p"
		assert migrated["jsonlExport"] is True
		assert migrated["mailTimeout"] == 60
		assert migrated["quiet"] is True
		assert migrated["webhookUrl"] == ""


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

