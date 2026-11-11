"""Account management: deletion, password change, folder operations."""

from utilities.etc import Credentials, p_print, Colours


def _login(mega, creds: Credentials) -> bool:
	"""Log into a MEGA account and return True on success."""
	try:
		mega.login(creds.email, creds.password)
		return True
	except Exception as e:
		p_print(f"Login failed for {creds.email}: {e}", Colours.FAIL)
		return False


def delete_account(credentials: Credentials) -> bool:
	"""Delete all files and cancel the MEGA account."""
	from services.upload import _safe_mega_session

	mega = _safe_mega_session(credentials)
	if mega is None:
		return False

	email = credentials.email
	p_print(f"Deleting account {email}...", Colours.WARNING)

	try:
		files = mega.get_files()
		for node_id, node_info in files.items():
			if node_info.get("t") != 2:
				continue
			try:
				mega.destroy(node_id)
				p_print(f"  Deleted {node_info.get('n', '?')}", Colours.OKCYAN)
			except Exception as e:
				p_print(f"  Failed to delete {node_id}: {e}", Colours.WARNING)
	except Exception as e:
		p_print(f"  Failed to list files: {e}", Colours.WARNING)

	try:
		mega.empty_trash()
	except Exception as e:
		p_print(f"  Failed to empty trash: {e}", Colours.WARNING)

	try:
		mega._api_request([{"a": "uc"}])
		p_print(f"Account {email} cancelled successfully.", Colours.OKGREEN)
		return True
	except Exception as e:
		p_print(f"Account cancellation failed: {e}", Colours.FAIL)
		return False


def change_password(credentials: Credentials, new_password: str) -> bool:
	"""Change the MEGA account password.

	MEGA does not expose a "set plaintext password" API command: the login
	hash is derived from a per-user salt (PBKDF2) and the SDK/mega.py have no
	verified password-change handshake. The previous ``{"a": "up", "pass":
	...}`` request was at best a no-op reporting success. Refuse explicitly
	instead of risking a silent failure.
	"""
	p_print(
		"Changing the MEGA password from MegaTemp is not supported: MEGA "
		"requires a salted key handshake that mega.py does not implement. "
		"Change it at https://mega.nz/ (Settings → Security) instead.",
		Colours.WARNING,
	)
	return False


def create_folder(credentials: Credentials, folder_name: str) -> bool:
	"""Create a folder in the MEGA account root."""
	from services.upload import _safe_mega_session

	mega = _safe_mega_session(credentials)
	if mega is None:
		return False

	p_print(f"Creating folder '{folder_name}'...", Colours.WARNING)
	try:
		mega.create_folder(folder_name)
		p_print(f"Folder '{folder_name}' created.", Colours.OKGREEN)
		return True
	except Exception as e:
		p_print(f"Folder creation failed: {e}", Colours.FAIL)
		return False
