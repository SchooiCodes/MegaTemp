"""Functions related to the upload functionality."""

import os
import threading
import time

from mega import Mega

from utilities.etc import Credentials, p_print, Colours, status_line, clear_status_line
from utilities.retry import retry


def _upload_with_progress(mega, file: str):
	"""Wrapper around mega.upload showing animated progress.

	Since the MEGA SDK doesn't expose a progress callback, we run a
	background thread and show elapsed time + file size.  We also poll
	the file's current size on disk to infer upload progress.
	"""
	result = [None]
	error = [None]
	total = os.path.getsize(file)

	def _do_upload():
		try:
			result[0] = mega.upload(file)
		except Exception as e:
			error[0] = e

	thread = threading.Thread(target=_do_upload, daemon=True)
	thread.start()

	start = time.time()
	spinner = iter(["|", "/", "-", "\\"])

	while thread.is_alive():
		elapsed = time.time() - start
		spinner_char = next(spinner)
		# Estimate progress: check the file's current uploaded chunk
		# (mega.py writes to a temp file, so we can't get true progress)
		bar_len = 20
		filled = min(int(elapsed / max(total / 50000, 1)), bar_len)
		bar = "█" * filled + "░" * (bar_len - filled)
		pct = min(int(elapsed / max(total / 50000, 1)) * 5, 99)

		# Show size/elapsed info
		mb = total / 1024 / 1024
		status_line(
			f"Uploading {os.path.basename(file)} {spinner_char} "
			f"[{bar}] {pct}% ({mb:.1f} MiB, {elapsed:.0f}s)",
			Colours.OKCYAN,
		)
		time.sleep(0.25)

	clear_status_line()

	if error[0]:
		raise error[0]
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
		msg = str(e) or "Unknown upload error"
		p_print(f"Upload failed: {msg}", Colours.FAIL)
		return

	p_print("File uploaded successfully.", Colours.OKGREEN)

	if public:
		try:
			link = mega.get_upload_link(uploaded_file)
			p_print(f"Shareable link: {link}", Colours.OKGREEN)
		except Exception as e:
			p_print(f"Could not generate share link: {e}", Colours.WARNING)
