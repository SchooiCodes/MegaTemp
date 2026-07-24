import pytest
import os

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

