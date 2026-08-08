import os
import subprocess
import sys

# Absolute path to the repo's main.py. Some CLI tests run main.py in an
# isolated temp cwd so they deterministically exercise the "no saved
# credentials" fast path instead of picking up real credentials (or network
# latencies) from the checkout directory.
MAIN_PY = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "main.py"))


def _run_main(args, cwd=None, timeout=30):
	return subprocess.run(
		[sys.executable, MAIN_PY, *args],
		capture_output=True,
		text=True,
		timeout=timeout,
		cwd=cwd,
	)


class TestMain:
	def test_module_imports(self):
		"""Verify all module-level imports in main.py work."""
		import importlib

		# Can't fully exec main.py because it parses CLI args at import time,
		# but we can check all its imports resolve (raises on failure)
		for mod in [
			"utilities.fs",
			"utilities.web",
			"utilities.etc",
			"utilities.menu",
			"services.alive",
			"services.extract",
			"services.upload",
		]:
			importlib.import_module(mod)

	def test_main_cli_help(self):
		"""Verify the CLI entrypoint produces help text."""
		import subprocess

		result = subprocess.run(
			[sys.executable, "main.py", "--help"],
			capture_output=True,
			text=True,
			timeout=30,
		)
		assert result.returncode == 0
		assert "usage:" in result.stdout
		assert "--keepalive" in result.stdout
		assert "--loop" in result.stdout
		assert "--extract" in result.stdout
		assert "--export-csv" in result.stdout

	def test_main_cli_version_info(self):
		"""The --help output should mention the tool name."""
		import subprocess

		result = subprocess.run(
			[sys.executable, "main.py", "--help"],
			capture_output=True,
			text=True,
			timeout=30,
		)
		assert "main.py" in result.stdout or "help" in result.stdout

	def test_main_verbose_flag_exits_gracefully(self):
		"""Running with -v should exit without a traceback.

		Note: main.py -v tries to launch a browser, so it may fail or
		hang. We just verify there's no Python traceback in stderr on
		the fast path, and use a short timeout to avoid hanging.
		"""
		import subprocess

		try:
			result = subprocess.run(
				[sys.executable, "main.py", "-v"],
				capture_output=True,
				text=True,
				timeout=15,
			)
			assert "Traceback" not in result.stderr, f"Crash: {result.stderr}"
		except subprocess.TimeoutExpired as e:
			# Timed out = browser launch delayed; not a code crash.
			# Convert bytes output to str for safe substring checks.
			out = (e.stdout or b"").decode("utf-8", errors="replace")
			err = (e.stderr or b"").decode("utf-8", errors="replace")
			assert "Traceback" not in out, f"Crash: {out}"
			assert "Traceback" not in err, f"Crash: {err}"


# ======================================================================
# download.py
# ======================================================================


class TestMainCLI:
	def test_main_list_cloud_no_crash(self, tmp_path):
		result = _run_main(["--list-cloud"], cwd=tmp_path)
		assert "Traceback" not in result.stderr

	def test_main_download_cloud_no_crash(self, tmp_path):
		result = _run_main(["--download-cloud", "test-id"], cwd=tmp_path)
		assert "Traceback" not in result.stderr

	def test_main_version_flag(self):
		import subprocess

		result = subprocess.run(
			[sys.executable, "main.py", "--version"],
			capture_output=True,
			text=True,
			timeout=10,
		)
		assert "v1.5.0" in result.stdout

	def test_main_provider_validation_valid(self):
		import subprocess

		result = subprocess.run(
			[sys.executable, "main.py", "--provider", "mailtm", "--version"],
			capture_output=True,
			text=True,
			timeout=10,
		)
		assert result.returncode == 0
		assert "v1.5.0" in result.stdout

	def test_main_provider_validation_invalid_stderr(self):
		import subprocess

		result = subprocess.run(
			[sys.executable, "main.py", "--provider", "doesnotexist"],
			capture_output=True,
			text=True,
			timeout=10,
		)
		assert result.returncode != 0
		# p_print may go to stdout or stderr depending on env, check both
		assert "Unknown provider" in result.stdout + result.stderr

	def test_main_json_requires_health(self):
		import subprocess

		result = subprocess.run(
			[sys.executable, "main.py", "--json"],
			capture_output=True,
			text=True,
			timeout=10,
		)
		assert result.returncode != 0
		assert "--json requires --health" in result.stdout + result.stderr

	def test_main_health_flag_no_crash(self, tmp_path):
		result = _run_main(["--health"], cwd=tmp_path)
		assert "Traceback" not in result.stderr
		assert (
			"No saved credentials" in result.stdout
			or "Health dashboard" in result.stdout
		)

	def test_main_health_json(self, tmp_path):
		result = _run_main(["--health", "--json"], cwd=tmp_path)
		assert result.returncode == 0
		import json as _json

		# main.py may print a startup line (e.g. browser auto-detect) before
		# the JSON payload; parse from the first '{'.
		payload = result.stdout[result.stdout.index("{") :]
		data = _json.loads(payload)
		assert "error" in data or "summary" in data
		assert "accounts" in data or "error" in data

	def test_main_export_flags_accepted(self):
		"""Export CLI flags should be accepted (no crash, no traceback)."""
		import subprocess

		for flag in ("--export-bitwarden", "--export-onepassword", "--export-keepass"):
			result = subprocess.run(
				[sys.executable, "main.py", flag],
				capture_output=True,
				text=True,
				timeout=30,
			)
			assert "Traceback" not in result.stderr, f"{flag} raised traceback"

	def test_main_webhook_flag_accepted(self):
		import subprocess

		result = subprocess.run(
			[
				sys.executable,
				"main.py",
				"--webhook-url",
				"http://example.com/hook",
				"--version",
			],
			capture_output=True,
			text=True,
			timeout=10,
		)
		assert result.returncode == 0

	def test_main_profile_flag_accepted(self):
		import subprocess

		result = subprocess.run(
			[sys.executable, "main.py", "--profile", "testcli", "--version"],
			capture_output=True,
			text=True,
			timeout=10,
		)
		assert result.returncode == 0

	def test_main_proxy_url_flag_accepted(self):
		import subprocess

		result = subprocess.run(
			[
				sys.executable,
				"main.py",
				"--proxy-url",
				"http://example.com/proxies.txt",
				"--version",
			],
			capture_output=True,
			text=True,
			timeout=10,
		)
		assert result.returncode == 0

	def test_main_quiet_flag(self):
		import subprocess

		result = subprocess.run(
			[sys.executable, "main.py", "--quiet", "--version"],
			capture_output=True,
			text=True,
			timeout=10,
		)
		assert result.returncode == 0
		assert "v1.5.0" in result.stdout


# ======================================================================
# utilities/exceptions.py — custom exception hierarchy
# ======================================================================
