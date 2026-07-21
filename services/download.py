"""Functions for listing and downloading files from MEGA cloud storage."""

import os

from mega import Mega

from utilities.etc import Credentials, p_print, Colours, separator
from utilities.menu import prompt_int, prompt_text, pause


def list_files(credentials: Credentials) -> list[dict]:
	"""List all files in the MEGA account root (node 2).

	Returns a list of dicts with keys: name, size, id.
	"""
	mega = Mega()
	try:
		mega.login(credentials.email, credentials.password)
	except Exception as e:
		p_print(f"Login failed for {credentials.email}: {e}", Colours.FAIL)
		return []

	try:
		files = mega.get_files_in_node(2)
	except Exception as e:
		p_print(f"Failed to list files: {e}", Colours.FAIL)
		return []

	result = []
	if files:
		for fid, info in files.items():
			result.append(
				{
					"id": fid,
					"name": info.get("a", {}).get("n", "unknown"),
					"size": info.get("s", 0),
				}
			)
	result.sort(key=lambda x: x["name"].lower())
	return result


def download_file(
	credentials: Credentials, file_id: str, dest_dir: str = "."
) -> str | None:
	"""Download a file from MEGA by its node ID. Returns local path or None."""
	mega = Mega()
	try:
		mega.login(credentials.email, credentials.password)
	except Exception as e:
		p_print(f"Login failed: {e}", Colours.FAIL)
		return None

	try:
		p_print(f"Downloading to {dest_dir} ...", Colours.HEADER)
		local_path = mega.download(file_id, dest_path=dest_dir)
		p_print(f"Downloaded to {local_path}", Colours.OKGREEN)
		return local_path
	except Exception as e:
		p_print(f"Download failed: {e}", Colours.FAIL)
		return None


def _action_browse_cloud(_executable_path, _config):
	"""TUI action: list files in the most recent account, offer download."""
	from utilities.fs import list_credentials

	creds_list = list_credentials()
	if not creds_list:
		p_print("No saved credentials.", Colours.WARNING)
		pause()
		return

	_fname, creds, _mtime = creds_list[0]
	p_print(f"Listing files for {creds.email} ...", Colours.HEADER)
	files = list_files(creds)
	if not files:
		p_print("No files found or account is empty.", Colours.WARNING)
		pause()
		return

	separator(f"Files in cloud ({len(files)})", Colours.HEADER)
	for idx, f in enumerate(files, start=1):
		size_mb = f["size"] / 1024 / 1024
		p_print(
			f"  {idx:>3}. {f['name']:<40} {size_mb:.1f} MiB",
			Colours.OKCYAN,
		)

	choice = prompt_int("Download which file? (0 to cancel)", 0, 0, len(files))
	if choice == 0:
		return
	selected = files[choice - 1]
	dest = prompt_text("Download directory", default=".")
	dest = os.path.expanduser(dest)
	if not os.path.isdir(dest):
		p_print(f"Directory not found: {dest}", Colours.FAIL)
		pause()
		return
	download_file(creds, selected["id"], dest)
	pause()
