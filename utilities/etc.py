"""All functions NOT related to the browser"""

import os
import shutil
import json
import time
import subprocess
from urllib.request import urlopen, Request
import sys
from mega import Mega
import psutil

from utilities.models import Colours, Credentials

VERSION = "v1.2.0"
UPDATE_URL = "https://api.github.com/repos/SchooiCodes/MegaTemp/tags"


def clear_tmp() -> bool:
	"""Clears tmp folder.

	If the initial deletion fails with a permission error (common when
	Chrome's crashpad holds file locks) we kill the locking processes and
	retry once. A missing tmp/ is treated as success.
	"""
	if not os.path.exists("tmp"):
		return True

	matches = ["CrashpadMetrics-active.pma", "CrashpadMetrics.pma"]

	for attempt in range(2):
		try:
			shutil.rmtree("tmp")
			return True
		except PermissionError:
			if attempt == 0:
				kill_process(matches)
			else:
				p_print(
					"Failed to clear tmp/ even after killing lock holders.",
					Colours.FAIL,
				)
				return False
		except FileNotFoundError:
			return True
		except OSError as e:
			p_print(f"Failed to clear tmp/: {e}", Colours.FAIL)
			return False

	return False


# Mapping from sys.platform to GitHub release asset name.
_RELEASE_ASSETS = {
	"win32": "MegaTemp-windows.exe",
	"linux": "MegaTemp-linux",
	"darwin": "MegaTemp-macos",
}

_RELEASES_URL = "https://api.github.com/repos/SchooiCodes/MegaTemp/releases"


def _latest_release_tag() -> str | None:
	"""Fetch the tag name of the latest GitHub release (not just any tag)."""
	try:
		req = Request(_RELEASES_URL + "?per_page=1", headers={"User-Agent": "MegaTemp"})
		with urlopen(req, timeout=10) as resp:
			data = json.loads(resp.read().decode())
		if isinstance(data, list) and len(data) > 0:
			return data[0].get("tag_name")
	except Exception:
		pass
	return None


def auto_update() -> None:
	"""Check for a newer release; if found, prompt, download, replace, restart.

	Only works when running as a frozen PyInstaller executable (``sys.frozen``).
	Source installations should use ``git pull`` instead.
	"""
	if not getattr(sys, "frozen", False):
		return  # source install — cannot self-replace

	asset = _RELEASE_ASSETS.get(sys.platform)
	if asset is None:
		return  # unknown platform

	latest = _latest_release_tag()
	if latest is None or latest == VERSION:
		return  # up to date or unreachable

	# Notify and ask
	p_print(
		f"New version available: {latest} (you have {VERSION})",
		Colours.WARNING,
	)
	answer = input("Update now? [Y/n]: ").strip().lower()
	if answer in ("n", "no"):
		return

	# Download
	url = f"https://github.com/SchooiCodes/MegaTemp/releases/download/{latest}/{asset}"
	download_path = sys.executable + ".new"
	p_print(f"Downloading {asset} ({latest}) ...", Colours.HEADER)
	try:
		req = Request(url, headers={"User-Agent": "MegaTemp"})
		with urlopen(req, timeout=180) as resp:
			total = int(resp.headers.get("Content-Length", 0))
			downloaded = 0
			with open(download_path, "wb") as f:
				while True:
					chunk = resp.read(65536)
					if not chunk:
						break
					f.write(chunk)
					downloaded += len(chunk)
					if total:
						pct = downloaded * 100 // total
						sys.stdout.write(f"\r  {pct}% ({downloaded // 1024} KiB)")
						sys.stdout.flush()
		print()
	except Exception as e:
		p_print(f"Download failed: {e}", Colours.FAIL)
		try:
			os.remove(download_path)
		except Exception:
			pass
		return

	os.chmod(download_path, 0o755)

	# Atomic replace: rename current exe to .old, new to current path.
	old_path = sys.executable + ".old"
	exe_path = sys.executable
	try:
		if os.path.exists(old_path):
			os.remove(old_path)
		os.rename(exe_path, old_path)
		os.rename(download_path, exe_path)
	except Exception as e:
		p_print(f"Replace failed: {e}", Colours.FAIL)
		try:
			os.remove(download_path)
		except Exception:
			pass
		return

	p_print(f"Updated to {latest}! Restarting...", Colours.OKGREEN)

	# Restart: on POSIX use execv (in-process replace); on Windows spawn new.
	if sys.platform == "win32":
		subprocess.Popen([exe_path] + sys.argv)
	else:
		os.execv(exe_path, sys.argv)
	sys.exit(0)


def delete_default(credentials: Credentials):
	"""Deletes the default welcome file.

	The default account has no welcome file (or the mega.py library call
	fails), so guard every step and treat "nothing to delete" as success.
	"""
	mega = Mega()
	try:
		mega.login(credentials.email, credentials.password)
	except Exception:
		return
	try:
		pdf = mega.get_files_in_node(2)
		if not pdf:
			return
		key = list(pdf.keys())[0]
		mega.destroy(key)
	except Exception:
		return


def reinstall_tenacity():
	"""Reinstalls tenacity because of a dependency problem within the mega.py library."""
	try:
		p_print("Reinstalling tenacity...", Colours.WARNING)
		pip = os.path.join(os.path.dirname(sys.executable), "pip")
		if not os.path.exists(pip):
			pip = "pip"
		ret = os.system(f"{pip} uninstall tenacity -y")
		if ret != 0:
			p_print(
				"Failed to uninstall old tenacity, continuing anyway...",
				Colours.WARNING,
			)
		ret = os.system(f"{pip} install tenacity")
		if ret != 0:
			p_print("Failed to install tenacity.", Colours.FAIL)
			sys.exit(1)
		clear_console()
		p_print("Reinstalled tenacity successfully!", Colours.OKGREEN)
		p_print("Please rerun the program.", Colours.WARNING)
		sys.exit(0)
	except Exception as e:
		p_print("Failed to reinstall tenacity!", Colours.FAIL)
		print(e)
		sys.exit(1)


def kill_process(matches: list):
	"""Kills processes holding files whose path contains one of `matches`.

	Used to release Chrome's crashpad lock files before clearing tmp. Never
	kills the current process or its own parents.
	"""
	current_pid = os.getpid()
	killed = False
	for process in psutil.process_iter():
		# Never kill ourselves (or we'd abort mid-cleanup).
		if process.pid == current_pid:
			continue
		try:
			for fh in process.open_files():
				if any(x in fh.path for x in matches):
					p_print(
						f"Killing process {process.name()} (pid {process.pid})...",
						Colours.WARNING,
					)
					process.kill()
					killed = True
					break
		except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
			continue

	if killed:
		p_print("Killed previous instances successfully!", Colours.OKGREEN)
	else:
		p_print("No matching processes to kill.", Colours.OKCYAN)


def p_print(
	text,
	colour,
):
	"""Prints text in colour."""
	print(colour + text + Colours.ENDC)


def clear_console():
	"""Clears console."""
	os.system("cls" if os.name == "nt" else "clear")


def separator(title: str = "", colour: str = Colours.HEADER, width: int = 60):
	"""Prints a horizontal rule, optionally with a centered title.

	Used to visually break the output into scannable phases, e.g.
	`──────────────── Registration attempt 1/4 ────────────────`.
	"""
	if title:
		title = f" {title} "
		pad = max(0, width - len(title))
		left = pad // 2
		right = pad - left
		line = ("─" * left) + title + ("─" * right)
	else:
		line = "─" * width
	print(colour + line + Colours.ENDC)


def status_line(text: str, colour: str = Colours.OKCYAN):
	"""Overwrites the current terminal line in place (no newline).

	Handy for high-frequency polling updates so we don't spam the scrollback.
	Call `clear_status_line()` (or print a newline) when finished.
	"""
	# \r returns to column 0; pad to clear any leftover from a longer prior line.
	sys.stdout.write("\r\033[K" + colour + text + Colours.ENDC)
	sys.stdout.flush()


def clear_status_line():
	"""Clears the in-place status line and moves to a fresh line."""
	sys.stdout.write("\r\033[K")
	sys.stdout.flush()


def elapsed(start: float) -> str:
	"""Returns a human-readable elapsed duration since a monotonic `start`."""
	seconds = time.monotonic() - start
	if seconds < 60:
		return f"{seconds:.1f}s"
	minutes, secs = divmod(seconds, 60)
	return f"{int(minutes)}m {secs:.1f}s"
