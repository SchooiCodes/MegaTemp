"""Functions related to the upload functionality."""

import os

from mega import Mega

from utilities.etc import Credentials, p_print, Colours


def upload_file(public: bool, file: str, credentials: Credentials):
	"""Uploads a file to the account and optionally prints a share link."""

	if not os.path.exists(file):
		p_print(f"File not found: {file}", Colours.FAIL)
		return

	mega = Mega()
	try:
		mega.login(credentials.email, credentials.password)
		p_print("Uploading file... this might take a while.", Colours.OKGREEN)
		uploaded_file = mega.upload(file)
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
