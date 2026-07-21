"""Functions related to the upload functionality."""

import os
import threading
import time

from mega import Mega

from utilities.etc import Credentials, p_print, Colours, status_line, clear_status_line


def _upload_with_progress(mega, file: str):
	"""Wrapper around mega.upload that shows a progress spinner.

	Mega's SDK does not expose a progress callback, so we run a
	background thread that prints a rotating spinner while the upload
	thread works.
	"""
	result = [None]
	error = [None]

	def _do_upload():
		try:
			result[0] = mega.upload(file)
		except Exception as e:
			error[0] = e

	thread = threading.Thread(target=_do_upload, daemon=True)
	thread.start()

	spinner = iter(["|", "/", "-", "\\"])
	while thread.is_alive():
		status_line(
			f"Uploading {os.path.basename(file)} {next(spinner)} ...", Colours.OKCYAN
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
		mega.login(credentials.email, credentials.password)
		file_size = os.path.getsize(file)
		p_print(
			f"Uploading {os.path.basename(file)} ({file_size / 1024 / 1024:.1f} MiB)...",
			Colours.HEADER,
		)
		uploaded_file = _upload_with_progress(mega, file)
	except Exception as e:
		p_print(f"Upload failed: {e}", Colours.FAIL)
		return

	p_print("File uploaded successfully.", Colours.OKGREEN)

	if public:
		try:
			link = mega.get_upload_link(uploaded_file)
			p_print(f"Shareable link: {link}", Colours.OKGREEN)
		except Exception as e:
			p_print(f"Could not generate share link: {e}", Colours.WARNING)
