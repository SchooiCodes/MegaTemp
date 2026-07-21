"""All functions NOT related to the browser"""

import os
import shutil
import json
import time
import subprocess
from dataclasses import dataclass
from urllib.request import urlopen, Request
import sys
from mega import Mega
import psutil

from utilities.models import Colours, Credentials

VERSION = "v1.3.0"
UPDATE_URL = "https://api.github.com/repos/SchooiCodes/MegaTemp/tags"


def notify(title: str, message: str) -> None:
	"""Show a desktop notification (best-effort, silent failure)."""
	import sys as _sys
	import subprocess as _sp

	if _sys.platform == "linux":
		try:
			_sp.run(
				["notify-send", title, message],
				timeout=5,
				capture_output=True,
			)
		except Exception:
			pass
	elif _sys.platform == "darwin":
		try:
			_sp.run(
				[
					"osascript",
					"-e",
					f'display notification "{message}" with title "{title}"',
				],
				timeout=5,
				capture_output=True,
			)
		except Exception:
			pass
	elif _sys.platform == "win32":
		try:
			_sp.run(
				[
					"powershell",
					"-Command",
					f'New-BurntToastNotification -Text "{title}", "{message}"',
				],
				timeout=5,
				capture_output=True,
			)
		except Exception:
			pass


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


class ProxyManager:
	"""Manages proxy rotation for browser launches.

	Supports a single proxy URL, a file of proxies (one per line), and
	per-attempt rotation mode. Proxies are validated for basic format
	correctness before being returned.
	"""

	def __init__(
		self, proxy: str = "", proxy_file: str = "", per_attempt: bool = False
	):
		self._proxies: list[str] = []
		self._per_attempt = per_attempt
		self._index = 0

		if proxy and proxy_file:
			p_print(
				"Both --proxy and --proxy-file provided; --proxy-file takes precedence.",
				Colours.WARNING,
			)

		if proxy_file:
			self._load_file(proxy_file)
		elif proxy:
			self._proxies = [proxy]

		if self._proxies:
			p_print(f"Loaded {len(self._proxies)} proxy/proxies.", Colours.OKCYAN)

	def _load_file(self, path: str) -> None:
		"""Load proxies from a file (one per line, # comments skipped)."""
		try:
			with open(path, "r", encoding="utf-8") as f:
				for line in f:
					line = line.strip()
					if not line or line.startswith("#"):
						continue
					self._proxies.append(line)
		except OSError as e:
			p_print(f"Failed to read proxy file {path}: {e}", Colours.FAIL)

	@staticmethod
	def _validate(proxy: str) -> bool:
		"""Basic format validation. Accepts http://user:pass@host:port etc."""
		if not proxy:
			return False
		if proxy.count("@") > 1:
			return False
		return True

	def get_proxy(self) -> str | None:
		"""Return the next proxy, or None if none are configured."""
		if not self._proxies:
			return None
		if self._per_attempt or len(self._proxies) == 1:
			proxy = self._proxies[self._index % len(self._proxies)]
			self._index += 1
			return proxy
		return self._proxies[0]

	@property
	def active(self) -> bool:
		return len(self._proxies) > 0

	@property
	def count(self) -> int:
		return len(self._proxies)

	def distribute(self, worker_count: int) -> list[str | None]:
		"""Return one proxy per worker (round-robin). Missing = None."""
		if not self._proxies:
			return [None] * worker_count
		return [self._proxies[i % len(self._proxies)] for i in range(worker_count)]


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


LOOP_STATE_FILE = "loop_state.json"


@dataclass
class LoopState:
	"""Persistent state for resuming interrupted loop runs."""

	total: int = 0
	completed: int = 0
	failed: int = 0
	started_at: float = 0.0


def save_checkpoint(state: LoopState) -> None:
	"""Write loop state to disk so interrupted runs can be resumed."""
	try:
		with open(LOOP_STATE_FILE, "w", encoding="utf-8") as f:
			json.dump(
				{
					"total": state.total,
					"completed": state.completed,
					"failed": state.failed,
					"started_at": state.started_at,
				},
				f,
			)
	except OSError:
		pass


def load_checkpoint() -> LoopState | None:
	"""Load a saved loop state, returning None if none exists."""
	try:
		with open(LOOP_STATE_FILE, "r", encoding="utf-8") as f:
			data = json.load(f)
		return LoopState(
			total=data.get("total", 0),
			completed=data.get("completed", 0),
			failed=data.get("failed", 0),
			started_at=data.get("started_at", 0.0),
		)
	except (OSError, json.JSONDecodeError):
		return None


def clear_checkpoint() -> None:
	"""Remove the checkpoint file after a successful run."""
	try:
		if os.path.exists(LOOP_STATE_FILE):
			os.remove(LOOP_STATE_FILE)
	except OSError:
		pass


def elapsed(start: float) -> str:
	"""Returns a human-readable elapsed duration since a monotonic `start`."""
	seconds = time.monotonic() - start
	if seconds < 60:
		return f"{seconds:.1f}s"
	minutes, secs = divmod(seconds, 60)
	return f"{int(minutes)}m {secs:.1f}s"
