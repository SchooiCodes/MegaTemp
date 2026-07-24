import pytest
import os

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

class TestUploadRetry:
	def test_upload_file_not_found(self):
		from services.upload import upload_file
		from utilities.models import Credentials

		creds = Credentials("test@test.test", "pw", "pw")
		upload_file(False, "/nonexistent/file.txt", creds)  # no crash


# ======================================================================
# main.py — CLI dispatch edge cases
# ======================================================================

