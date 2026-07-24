"""Functions for listing and downloading files from MEGA cloud storage."""

import os

from utilities.etc import Credentials, p_print, Colours, separator
from utilities.menu import prompt_int, prompt_path, pause
from utilities.retry import retry


def list_files(credentials: Credentials) -> list[dict]:
	"""List all files in the MEGA account root (node 2)."""
	from services.upload import _safe_mega_session
	mega = _safe_mega_session(credentials)
	if mega is None:
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
					),
				}
			)
	result.sort(key=lambda x: x["name"].lower())
	return result


def download_file(
	credentials: Credentials, node: dict, dest_dir: str = "."
) -> str | None:
	"""Download a file from MEGA by its node dict. Returns local path or None."""
	from services.upload import _safe_mega_session
	mega = _safe_mega_session(credentials)
	if mega is None:
		return None

	try:
		p_print(f"Downloading to {dest_dir} ...", Colours.HEADER)
		import threading

		result = [None]
		exception = [None]

		def _run():
			try:
				result[0] = retry(label="mega.download", max_attempts=3)(
				    mega.download
				)(node, dest_path=dest_dir)
			except Exception as e:
				exception[0] = e

		t = threading.Thread(target=_run, daemon=True)
		t.start()
		t.join(timeout=300)
		if t.is_alive():
			p_print("Download timed out (5 min limit).", Colours.FAIL)
			return None
		if exception[0]:
			raise exception[0]
		local_path = result[0]
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
