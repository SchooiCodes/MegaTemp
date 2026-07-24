"""All functions NOT related to the browser"""

import os
import shutil
import json
import time
import subprocess
from dataclasses import dataclass
from urllib.request import urlopen, Request
import sys
import psutil
import contextvars
from contextlib import contextmanager

from utilities.models import Colours, Credentials

VERSION = "v1.4.0"
UPDATE_URL = "https://api.github.com/repos/SchooiCodes/MegaTemp/tags"


def notify(title: str, message: str) -> None:
	"""Show a desktop notification (best-effort, fire-and-forget)."""
	if _QUIET:
		return
	import sys as _sys
	import subprocess as _sp
	import threading as _th

	def _fire():
		try:
			if _sys.platform == "linux":
				_sp.run(
					["notify-send", title, message],
					timeout=5,
					capture_output=True,
				)
			elif _sys.platform == "darwin":
				_sp.run(
					[
						"osascript",
						"-e",
						f'display notification "{message}" with title "{title}"',
					],
					timeout=5,
					capture_output=True,
				)
			elif _sys.platform == "win32":
				import ctypes as _ct
				_ct.windll.user32.MessageBoxW(0, message, title, 0x40 | 0x1000)
		except Exception:
			pass

	_th.Thread(target=_fire, daemon=True).start()


def _find_tmp_lock_files(tmp_dir: str) -> list[str]:
	"""Find crashpad lock files inside tmp_dir that may block deletion."""
	matches = []
	try:
		for root, _dirs, files in os.walk(tmp_dir):
			for f in files:
				if f.endswith(".pma") or f.endswith(".lock") or "Crashpad" in f:
					matches.append(os.path.join(root, f))
	except OSError:
		pass
	return matches if matches else []


def clear_tmp() -> bool:
	"""Clears tmp folder.

	If the initial deletion fails with a permission error (common when
	Chrome's crashpad holds file locks) we kill the locking processes and
	retry once. A missing tmp/ is treated as success.
	"""
	tmp_dir = "tmp"
	if not os.path.exists(tmp_dir):
		return True

	for attempt in range(2):
		try:
			shutil.rmtree(tmp_dir)
			return True
		except PermissionError:
			if attempt == 0:
				kill_process(_find_tmp_lock_files(tmp_dir))
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
	def fetch_from_url(url: str, timeout: int = 15) -> list[str]:
		"""Fetch a proxy list from a URL (one proxy per line).

		Supports plain-text lists and JSON arrays of proxy strings.
		Returns a list of valid-looking proxy URLs.
		"""
		try:
			import urllib.request as _ur
			import json as _json
			req = _ur.Request(url, headers={"User-Agent": "MegaTemp"})
			with _ur.urlopen(req, timeout=timeout) as resp:
				raw = resp.read().decode("utf-8", errors="replace")
		except Exception as e:
			p_print(f"Failed to fetch proxies from {url}: {e}", Colours.FAIL)
			return []

		proxies: list[str] = []
		# Try JSON first (array of strings)
		raw_stripped = raw.strip()
		if raw_stripped.startswith("["):
			try:
				data = _json.loads(raw_stripped)
				if isinstance(data, list):
					for item in data:
						if isinstance(item, str) and item.strip():
							proxies.append(item.strip())
				if proxies:
					return proxies
			except _json.JSONDecodeError:
				pass

		# Fall back to line-by-line parsing
		for line in raw.splitlines():
			line = line.strip()
			if not line or line.startswith("#"):
				continue
			if ProxyManager._validate(line):
				proxies.append(line)
		return proxies

	def fetch_and_add(self, url: str) -> int:
		"""Fetch proxies from a URL and append them to the internal list."""
		new_proxies = self.fetch_from_url(url)
		self._proxies.extend(new_proxies)
		if new_proxies:
			p_print(f"Fetched {len(new_proxies)} proxies from {url}", Colours.OKCYAN)
		return len(new_proxies)

	@staticmethod
	def _validate(proxy: str) -> bool:
		if not proxy:
			return False
		if proxy.count("@") > 1:
			return False
		from urllib.parse import urlparse
		try:
			parsed = urlparse(proxy)
			if parsed.scheme not in ("http", "https", "socks4", "socks5", ""):
				return False
			if not parsed.hostname:
				return False
			return True
		except Exception:
			return False

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

	def test_proxy(self, proxy: str, timeout: int = 10) -> bool:
		"""Test a proxy by making a request through it to a reliable endpoint."""
		try:
			import urllib.request as _ur
			req = _ur.Request("http://httpbin.org/ip", headers={"User-Agent": "MegaTemp"})
			handler = _ur.ProxyHandler({"http": proxy, "https": proxy})
			opener = _ur.build_opener(handler)
			resp = opener.open(req, timeout=timeout)
			return resp.status == 200
		except Exception:
			return False

	def test_all(self, timeout: int = 10) -> list[tuple[str, bool]]:
		"""Test all loaded proxies and return (proxy, ok) pairs."""
		results = []
		for p in self._proxies:
			ok = self.test_proxy(p, timeout=timeout)
			results.append((p, ok))
		return results

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
	checksum_url = url + ".sha256"
	download_path = sys.executable + ".new"
	p_print(f"Downloading {asset} ({latest}) ...", Colours.HEADER)

	# Fetch expected SHA256 checksum (best-effort)
	expected_hash: str | None = None
	try:
		creq = Request(checksum_url, headers={"User-Agent": "MegaTemp"})
		with urlopen(creq, timeout=15) as cresp:
			cdata = cresp.read().decode("utf-8", errors="replace").strip()
			# Format: "sha256hash  filename"
			expected_hash = cdata.split()[0] if cdata else None
	except Exception:
		pass

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

	# Verify SHA256 checksum if available.
	if expected_hash:
		import hashlib as _hl
		actual_hash = _hl.sha256()
		with open(download_path, "rb") as _fh:
			while True:
				chunk = _fh.read(65536)
				if not chunk:
					break
				actual_hash.update(chunk)
		if actual_hash.hexdigest() != expected_hash:
			p_print(
				f"SHA256 mismatch! Expected {expected_hash}, "
				f"got {actual_hash.hexdigest()}. Aborting update.",
				Colours.FAIL,
			)
			try:
				os.remove(download_path)
			except Exception:
				pass
			return
		p_print("SHA256 checksum verified.", Colours.OKGREEN)

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


def delete_default(credentials: Credentials) -> None:
	"""Deletes the default welcome file.

	The default account has no welcome file (or the mega.py library call
	fails), so guard every step and treat "nothing to delete" as success.
	"""
	from services.upload import get_mega_session
	try:
		mega = get_mega_session(credentials)
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


def reinstall_tenacity() -> None:
	"""Reinstalls tenacity because of a dependency problem within the mega.py library."""
	try:
		p_print("Reinstalling tenacity...", Colours.WARNING)
		pip = os.path.join(os.path.dirname(sys.executable), "pip")
		if not os.path.exists(pip):
			pip = "pip"
		ret = subprocess.run([pip, "uninstall", "tenacity", "-y"], capture_output=True).returncode
		if ret != 0:
			p_print(
				"Failed to uninstall old tenacity, continuing anyway...",
				Colours.WARNING,
			)
		ret = subprocess.run([pip, "install", "tenacity"], capture_output=True).returncode
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


def kill_process(matches: list) -> None:
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


# ── Quiet mode ────────────────────────────────────────────────────────
# When set, p_print() / separator() only show WARNING/FAIL messages.
_QUIET = False


def set_quiet(value: bool) -> None:
	"""Enable/disable quiet mode (suppresses non-essential output)."""
	global _QUIET
	_QUIET = value


# ── Per-task print buffering ──────────────────────────────────────────
# When set, p_print() / separator() capture output into this list
# instead of printing immediately.  Workers flush atomically so
# parallel output doesn't interleave.
_print_buffer: contextvars.ContextVar[list | None] = contextvars.ContextVar(
	"_print_buffer", default=None
)


def _capture_or_print(text: str, colour: str) -> None:
	"""Write *text* to the per-task buffer, or print directly."""
	if _QUIET and colour not in (Colours.FAIL, Colours.WARNING):
		return
	buf = _print_buffer.get()
	if buf is not None:
		buf.append((text, colour))
	else:
		print(colour + text + Colours.ENDC)


def flush_print_buffer() -> list[tuple[str, str]] | None:
	"""Flush and return the captured lines (caller prints them)."""
	buf = _print_buffer.get()
	if buf is not None:
		lines = buf[:]
		buf.clear()
		return lines
	return None


@contextmanager
def capture_worker_output() -> list:
	"""Context manager: capture ``p_print``/``separator`` calls into a list.

	The captured list is yielded so the caller can flush it atomically::

	    with capture_worker_output() as buf:
	        do_work()
	    # buf contains [(text, colour), ...]
	    for text, colour in buf:
	        print(colour + text + Colours.ENDC)
	"""
	buf: list[tuple[str, str]] = []
	token = _print_buffer.set(buf)
	try:
		yield buf
	finally:
		_print_buffer.reset(token)


# ── Print ─────────────────────────────────────────────────────────────


def p_print(text: str, colour: str = Colours.OKGREEN) -> None:
	"""Prints text in colour, or buffers it under a PrintCollector."""
	_capture_or_print(text, colour)


def separator(title: str = "", colour: str = Colours.HEADER, width: int = 60) -> None:
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
	_capture_or_print(line, colour)


def send_webhook(url: str, event: str, data: dict) -> None:
	"""POST a JSON payload to a webhook URL (best-effort, silent failure)."""
	if _QUIET:
		return
	if not url:
		return
	try:
		import urllib.request as _ur
		import json as _json
		payload = _json.dumps({"event": event, "data": data}).encode()
		req = _ur.Request(
			url,
			data=payload,
			headers={
				"Content-Type": "application/json",
				"User-Agent": "MegaTemp",
			},
		)
		_ur.urlopen(req, timeout=10)
	except Exception:
		pass


def clear_console() -> None:
	"""Clears console using ANSI escape sequences."""
	sys.stdout.write("\x1b[2J\x1b[H")
	sys.stdout.flush()


def status_line(text: str, colour: str = Colours.OKCYAN) -> None:
	"""Overwrites the current terminal line in place (no newline).

	Handy for high-frequency polling updates so we don't spam the scrollback.
	Call `clear_status_line()` (or print a newline) when finished.
	"""
	# \r returns to column 0; pad to clear any leftover from a longer prior line.
	sys.stdout.write("\r\033[K" + colour + text + Colours.ENDC)
	sys.stdout.flush()


def clear_status_line() -> None:
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
