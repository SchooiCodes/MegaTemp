"""Functions for listing and downloading files from MEGA cloud storage."""

import os

from mega import Mega

from utilities.etc import Credentials, p_print, Colours, separator
from utilities.menu import prompt_int, prompt_path, pause
from utilities.retry import retry


def list_files(credentials: Credentials) -> list[dict]:
	"""List all files in the MEGA account root (node 2).

	Returns a list of dicts with keys: name, size, id, node (full node object).
	"""
	mega = Mega()
	try:
		retry(label="MEGA login", max_attempts=3)(mega.login)(
			credentials.email, credentials.password
		)
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
					"node": (
						fid,
						info,
					),  # tuple (node_id, node_info) for mega.download()
				}
			)
	result.sort(key=lambda x: x["name"].lower())
	return result


def download_file(
	credentials: Credentials, node: dict, dest_dir: str = "."
) -> str | None:
	"""Download a file from MEGA by its node dict. Returns local path or None.

	``node`` must be the full node dict from ``mega.get_files_in_node()``
	(including the ``a``, ``h``, ``k``, ``s``, ``i`` attributes).
	"""
	mega = Mega()
	try:
		mega.login(credentials.email, credentials.password)
	except Exception as e:
		p_print(f"Login failed: {e}", Colours.FAIL)
		return None

	try:
		p_print(f"Downloading to {dest_dir} ...", Colours.HEADER)
		local_path = mega.download(node, dest_path=dest_dir)
		p_print(f"Downloaded to {local_path}", Colours.OKGREEN)
		return local_path
	except Exception as e:
		p_print(f"Download failed: {e}", Colours.FAIL)
		return None


def _action_browse_cloud(_executable_path, _config):
	"""TUI action: list files in a chosen account, offer download."""
	from utilities.fs import list_credentials

	creds_list = list_credentials()
	if not creds_list:
		p_print("No saved credentials.", Colours.WARNING)
		pause()
		return

	# Let the user pick which account to browse.
	from utilities.menu import prompt_int as _prompt_int

	separator("Select account to browse", Colours.HEADER)
	for idx, (_fname, c, _mtime) in enumerate(creds_list, start=1):
		tag = f" [{c.tags}]" if c.tags else ""
		p_print(f"  {idx:>3}. {c.email}{tag}", Colours.OKCYAN)
	go_back_idx = len(creds_list) + 1
	p_print(f"  {go_back_idx:>3}. Go back", Colours.WARNING)
	choice = _prompt_int("Account", 1, 1, go_back_idx)
	if choice == go_back_idx:
		return
	_fname, creds, _mtime = creds_list[choice - 1]
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
	dest = prompt_path("Download directory", default=".", must_exist=True)
	dest = os.path.expanduser(dest)
	if not os.path.isdir(dest):
		p_print(f"Directory not found: {dest}", Colours.FAIL)
		pause()
		return
	download_file(creds, selected["node"], dest)
	pause()
