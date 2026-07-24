import pytest
import os

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

