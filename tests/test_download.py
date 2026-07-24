import pytest
import sys


class TestDownload:
	@pytest.fixture(autouse=True)
	def _mock_mega(self, monkeypatch):
		monkeypatch.setattr("services.upload._safe_mega_session", lambda _: None)

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
		result = download_file(creds, {"a": {"n": "test"}, "s": 0}, "/tmp")
		assert result is None

	def test_list_cloud_flag_no_creds(self):
		import subprocess

		result = subprocess.run(
			[sys.executable, "main.py", "--list-cloud"],
			capture_output=True,
			text=True,
			timeout=30,
		)
		assert "Traceback" not in result.stderr

	def test_download_cloud_flag_no_creds(self):
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
