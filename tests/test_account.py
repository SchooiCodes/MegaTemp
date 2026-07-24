import pytest


class TestAccountServices:
	@pytest.fixture(autouse=True)
	def _mock_mega(self, monkeypatch):
		monkeypatch.setattr("services.upload._safe_mega_session", lambda _: None)

	def test_delete_account_no_creds(self):
		from services.account import delete_account
		from utilities.models import Credentials

		creds = Credentials("test@test.test", "pw", "pw")
		result = delete_account(creds)
		assert result is False

	def test_change_password_no_creds(self):
		from services.account import change_password
		from utilities.models import Credentials

		creds = Credentials("test@test.test", "pw", "pw")
		result = change_password(creds, "newpw123")
		assert result is False

	def test_create_folder_no_creds(self):
		from services.account import create_folder
		from utilities.models import Credentials

		creds = Credentials("test@test.test", "pw", "pw")
		create_folder(creds, "test_folder")  # no crash
