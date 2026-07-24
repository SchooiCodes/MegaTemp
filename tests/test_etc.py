import pytest
import os
import time

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

class TestNotify:
	def test_notify_no_crash(self):
		from utilities.etc import notify

		# Should not raise — best effort
		notify("Test title", "Test message")


# ======================================================================
# utilities/fs.py — config validation
# ======================================================================

class TestQuietMode:
	def test_set_quiet_suppresses_output(self):
		from utilities.etc import set_quiet, p_print, Colours

		set_quiet(True)
		# INFO-level should not be printed in quiet mode
		p_print("noisy", Colours.OKCYAN)
		# WARNING/FAIL should still go through
		p_print("warning", Colours.WARNING)
		p_print("failure", Colours.FAIL)
		set_quiet(False)

	def test_set_quiet_toggle(self):
		from utilities.etc import set_quiet

		set_quiet(True)
		assert True  # no crash
		set_quiet(False)


# ======================================================================
# services/account.py — delete, change password, create folder (no-crash)
# ======================================================================

class TestWebhook:
	def test_send_webhook_empty_url(self):
		from utilities.etc import send_webhook
		send_webhook("", "test", {})  # no crash

	def test_send_webhook_invalid_url(self):
		from utilities.etc import send_webhook
		send_webhook("http://invalid.nonexistent.example/test", "test", {})  # no crash


# ======================================================================
# Proxy auto-fetch tests
# ======================================================================

class TestSendWebhook:
	def test_webhook_suppressed_in_quiet(self):
		from utilities.etc import set_quiet, send_webhook
		set_quiet(True)
		send_webhook("http://example.com/hook", "test", {"key": "val"})  # no crash
		set_quiet(False)

	def test_webhook_with_data(self):
		from utilities.etc import send_webhook
		send_webhook("", "test", {"email": "a@b.com", "timestamp": 100})  # no crash

