"""Functions related to the upload functionality."""

import os
import threading
import time

from utilities.etc import Credentials, p_print, Colours, status_line, clear_status_line
from utilities.retry import retry


def _format_speed(bytes_per_sec: float) -> str:
	if bytes_per_sec >= 1_000_000:
		return f"{bytes_per_sec / 1_000_000:.1f} MB/s"
	if bytes_per_sec >= 1_000:
		return f"{bytes_per_sec / 1_000:.0f} KB/s"
	return f"{bytes_per_sec:.0f} B/s"


def _format_eta(seconds: float) -> str:
	if seconds <= 0:
		return "—"
	if seconds < 60:
		return f"{seconds:.0f}s"
	m = int(seconds // 60)
	s = int(seconds % 60)
	return f"{m}m {s:02d}s"


def _upload_with_progress(mega, file: str):
	"""Wrapper around mega.upload showing upload status."""
	result = [None]
	error = [None]
	start = [time.time()]

	def _do_upload():
		try:
			result[0] = retry(label="mega.upload", max_attempts=2)(mega.upload)(
				file
			)
		except Exception as e:
			error[0] = e

	thread = threading.Thread(target=_do_upload, daemon=True)
	thread.start()

	while thread.is_alive():
		elapsed = time.time() - start[0]
		status_line(
			f"Uploading {os.path.basename(file)}... ({int(elapsed)}s elapsed)",
			Colours.OKCYAN,
		)
		time.sleep(0.5)

	clear_status_line()

	thread.join(timeout=5)
	if error[0]:
		raise error[0]
	if result[0] is None:
		raise RuntimeError(
			"mega.upload() returned None — the account may have 0 GB quota"
		)
	return result[0]


def upload_file(public: bool, file: str, credentials: Credentials) -> None:
	"""Uploads a file to the account and optionally prints a share link."""

	if not os.path.exists(file):
		p_print(f"File not found: {file}", Colours.FAIL)
		return

	try:
		mega = get_mega_session(credentials)
	except Exception as e:
		p_print(f"Login failed for {credentials.email}: {e}", Colours.FAIL)
		return

	try:
		file_size = os.path.getsize(file)
		p_print(
			f"Uploading {os.path.basename(file)} ({file_size / 1024 / 1024:.1f} MiB)...",
			Colours.HEADER,
		)
		uploaded_file = _upload_with_progress(mega, file)
	except Exception as e:
		exc_name = type(e).__name__
		msg = str(e) or "Unknown upload error"
		p_print(f"Upload failed [{exc_name}]: {msg}", Colours.FAIL)
		return

	p_print("File uploaded successfully.", Colours.OKGREEN)

	if public:
		try:
			link = mega.get_upload_link(uploaded_file)
			p_print(f"Shareable link: {link}", Colours.OKGREEN)
		except Exception as e:
			p_print(f"Could not generate share link: {e}", Colours.WARNING)


# Cache a single Mega() session per credentials set so directory uploads
# don't pay a fresh login cost per file.
_mega_sessions: dict[tuple[str, str], object] = {}
_mega_sessions_lock = threading.Lock()


def get_mega_session(credentials: Credentials) -> object:
	"""Return a cached Mega() instance logged in with the given credentials.
	Raises on login failure so callers can catch and act accordingly.
	"""
	key = (credentials.email, credentials.password)
	if key not in _mega_sessions:
		with _mega_sessions_lock:
			if key not in _mega_sessions:
				from mega import Mega
				mega = Mega()
				retry(label="MEGA login", max_attempts=3)(mega.login)(
					credentials.email, credentials.password
				)
				_mega_sessions[key] = mega
	return _mega_sessions[key]


def _safe_mega_session(credentials: Credentials):
	"""Return a Mega() instance or None if credentials don't authenticate."""
	try:
		return get_mega_session(credentials)
	except Exception:
		return None


def _upload_with_session(public: bool, file: str, mega):
	"""Upload a single file using an already-logged-in Mega() instance."""
	if not os.path.exists(file):
		p_print(f"File not found: {file}", Colours.FAIL)
		return

	try:
		file_size = os.path.getsize(file)
		p_print(
			f"Uploading {os.path.basename(file)} ({file_size / 1024 / 1024:.1f} MiB)...",
			Colours.HEADER,
		)
		uploaded_file = _upload_with_progress(mega, file)
	except Exception as e:
		exc_name = type(e).__name__
		msg = str(e) or "Unknown upload error"
		p_print(f"Upload failed [{exc_name}]: {msg}", Colours.FAIL)
		return

	p_print("File uploaded successfully.", Colours.OKGREEN)

	if public:
		try:
			link = mega.get_upload_link(uploaded_file)
			p_print(f"Shareable link: {link}", Colours.OKGREEN)
		except Exception as e:
			p_print(f"Could not generate share link: {e}", Colours.WARNING)
