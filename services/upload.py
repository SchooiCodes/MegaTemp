"""Functions related to the upload functionality."""

import os
import threading
import time

from mega import Mega

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
	"""Wrapper around mega.upload showing real-time progress with speed & ETA."""
	result = [None]
	error = [None]
	total = os.path.getsize(file)
	progress = [0]  # shared state: bytes uploaded (updated via callback)

	def _progress(bytes_up, _total):
		progress[0] = bytes_up

	def _do_upload():
		try:
			result[0] = retry(label="mega.upload", max_attempts=2)(mega.upload)(
				file, progress_callback=_progress
			)
		except Exception as e:
			error[0] = e

	thread = threading.Thread(target=_do_upload, daemon=True)
	thread.start()

	start = time.time()
	timeout = max(total // 50000, 30)  # at least 30s, scales with file size

	while thread.is_alive():
		elapsed = time.time() - start
		if elapsed > timeout:
			error[0] = TimeoutError(
				f"Upload timed out after {int(elapsed)}s ({total // 1024 // 1024} MiB)"
			)
			break

		bytes_up = progress[0]
		speed = bytes_up / elapsed if elapsed > 0 and bytes_up > 0 else 0
		pct = bytes_up / total * 100 if total > 0 else 0
		remaining = (total - bytes_up) / speed if speed > 0 else 0

		bar_len = 20
		filled = int(pct / 100 * bar_len)
		bar = "█" * filled + "░" * (bar_len - filled)

		mb_total = total / 1024 / 1024
		speed_str = _format_speed(speed)
		eta_str = _format_eta(remaining) if bytes_up > 0 else "starting..."
		status_line(
			f"Uploading {os.path.basename(file)} [{bar}] {pct:.0f}% "
			f"({mb_total:.1f} MiB @ {speed_str}, ETA {eta_str})",
			Colours.OKCYAN,
		)
		time.sleep(0.25)

	clear_status_line()

	thread.join(timeout=5)
	if error[0]:
		raise error[0]
	if result[0] is None:
		raise RuntimeError(
			"mega.upload() returned None — the account may have 0 GB quota"
		)
	return result[0]


def upload_file(public: bool, file: str, credentials: Credentials):
	"""Uploads a file to the account and optionally prints a share link."""

	if not os.path.exists(file):
		p_print(f"File not found: {file}", Colours.FAIL)
		return

	mega = Mega()
	try:
		retry(label="MEGA login", max_attempts=3)(mega.login)(
			credentials.email, credentials.password
		)
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
