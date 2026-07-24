import pytest
import os

class TestPasswordManagerExports:
	def test_export_bitwarden_no_folder(self, isolated_fs):
		from services.extract import export_bitwarden_csv

		export_bitwarden_csv()  # no crash

	def test_export_bitwarden_empty_folder(self, isolated_fs):
		from services.extract import export_bitwarden_csv

		os.makedirs("credentials", exist_ok=True)
		export_bitwarden_csv()  # no crash

	def test_export_onepassword_no_folder(self, isolated_fs):
		from services.extract import export_onepassword_csv

		export_onepassword_csv()  # no crash

	def test_export_bitwarden_with_creds(self, isolated_fs):
		from services.extract import export_bitwarden_csv
		from utilities.models import Credentials
		from utilities.fs import save_credentials

		os.makedirs("credentials", exist_ok=True)
		creds = Credentials("user@test.test", "mailpw", "megapw")
		save_credentials(creds, "")
		path = export_bitwarden_csv()
		assert os.path.exists(path)

	def test_export_onepassword_with_creds(self, isolated_fs):
		from services.extract import export_onepassword_csv
		from utilities.models import Credentials
		from utilities.fs import save_credentials

		os.makedirs("credentials", exist_ok=True)
		creds = Credentials("user2@test.test", "mailpw", "megapw")
		save_credentials(creds, "")
		path = export_onepassword_csv()
		assert os.path.exists(path)

	def test_export_bitwarden_content(self, isolated_fs):
		from services.extract import export_bitwarden_csv
		from utilities.models import Credentials
		from utilities.fs import save_credentials

		os.makedirs("credentials", exist_ok=True)
		import csv as _csv
		creds = Credentials("bob@test.test", "mpw", "secret123")
		save_credentials(creds, "")
		path = export_bitwarden_csv()
		with open(path) as f:
			rows = list(_csv.reader(f))
		assert len(rows) >= 2  # header + data
		assert rows[1][5] == "https://mega.nz"
		assert rows[1][6] == "bob@test.test"

	def test_export_onepassword_content(self, isolated_fs):
		from services.extract import export_onepassword_csv
		from utilities.models import Credentials
		from utilities.fs import save_credentials

		os.makedirs("credentials", exist_ok=True)
		import csv as _csv
		creds = Credentials("alice@test.test", "mpw", "megapw")
		save_credentials(creds, "")
		path = export_onepassword_csv()
		with open(path) as f:
			rows = list(_csv.reader(f))
		assert len(rows) >= 2
		assert "alice@test.test" in rows[1][2]


# ======================================================================
# Webhook tests
# ======================================================================

class TestKeePassExport:
	def test_keepass_no_folder(self, isolated_fs):
		from services.extract import export_keepass_csv
		export_keepass_csv()  # no crash

	def test_keepass_with_creds(self, isolated_fs):
		from services.extract import export_keepass_csv
		from utilities.models import Credentials
		from utilities.fs import save_credentials
		os.makedirs("credentials", exist_ok=True)
		creds = Credentials("kp@test.test", "mpw", "kpw")
		save_credentials(creds, "")
		path = export_keepass_csv()
		assert os.path.exists(path)

	def test_keepass_content(self, isolated_fs):
		from services.extract import export_keepass_csv
		from utilities.models import Credentials
		from utilities.fs import save_credentials
		import csv as _csv
		os.makedirs("credentials", exist_ok=True)
		creds = Credentials("kpuser@test.test", "mpw", "kppass")
		save_credentials(creds, "")
		path = export_keepass_csv()
		with open(path) as f:
			rows = list(_csv.reader(f))
		assert len(rows) >= 2
		assert rows[0][1] == "Title"
		assert rows[1][1] == "kpuser@test.test"
		assert rows[1][3] == "kppass"
		assert rows[1][4] == "https://mega.nz"


# ======================================================================
# Additional edge case tests
# ======================================================================

