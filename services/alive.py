"""Functions related to the keepalive functionality."""

import os
import json
import time
from concurrent.futures import ThreadPoolExecutor

import utilities.compat  # noqa: F401 — restores asyncio.coroutine for tenacity

from mega import Mega
from mega.errors import RequestError

from utilities.etc import p_print, Colours, elapsed, separator


def _process_one(file: str, idx: int, total: int, verbose: bool, prune: bool, max_retries: int) -> dict:
	"""Process a single credential file for keepalive (runs in a thread)."""
	path = f"./credentials/{file}"
	result = {
		"idx": idx,
		"total": total,
		"email": "",
		"status": "FAIL",
		"quota": "-",
		"age": "?",
		"path": path,
		"prune": prune,
		"data": None,
	}
	try:
		with open(path, "r", encoding="utf-8") as f:
			data = json.load(f)
	except (json.JSONDecodeError, OSError) as e:
		p_print(f"Skipping unreadable credential file {file}: {e}", Colours.WARNING)
		return result

	email = data.get("email")
	password = data.get("password")
	if not email or not password:
		p_print(f"Skipping {file}: missing email/password.", Colours.WARNING)
		return result

	result["email"] = email
	result["data"] = data

	# Attempt login with retries (fresh Mega() per account).
	status = "FAIL"
	quota_gb = 0.0
	for attempt in range(1, max_retries + 1):
		try:
			mega = Mega()
			mega.login(email, password)
			quota_left = mega.get_quota() / 1024
			quota_gb = quota_left
			status = "OK"
			break
		except (RequestError, json.JSONDecodeError):
			if attempt < max_retries:
				sleep_secs = attempt * 0.5
				p_print(
					f"  Retry {attempt}/{max_retries} for {email} in {sleep_secs}s...",
					Colours.WARNING,
				)
				time.sleep(sleep_secs)
		except Exception as e:
			p_print(f"{idx}/{total} Error with {email}: {e}", Colours.FAIL)
			status = "FAIL"
			break

	result["status"] = status
	result["quota"] = f"{quota_gb:.1f} GB" if quota_gb else "-"

	if status == "OK":
		p_print(f"{idx}/{total} OK  {email}", Colours.OKGREEN)
		if verbose:
			p_print(f"    {quota_gb:.2f} GB left", Colours.OKGREEN)
		data["lastLogin"] = time.time()
	else:
		p_print(f"{idx}/{total} FAIL {email}", Colours.FAIL)

	# Compute age from credential file modification time.
	try:
		age_secs = time.time() - os.path.getmtime(path)
		age_days = age_secs / 86400
		age_str = f"{age_days:.0f}d" if age_days >= 1 else f"{age_secs / 3600:.0f}h"
	except OSError:
		age_str = "?"
	result["age"] = age_str

	return result


def keepalive(verbose: bool, prune: bool = False, max_retries: int = 3) -> None:
	"""Keep the generated accounts alive by logging in.

	Args:
		verbose: Show storage quota per account.
		prune: Delete credential files for accounts that fail login.
		max_retries: Retry attempts per account with exponential backoff.
	"""
	from utilities.fs import CREDENTIALS_DIR
	if not os.path.isdir(CREDENTIALS_DIR):
		p_print(
			"No credentials found, please remove all arguments and try again.",
			Colours.FAIL,
		)
		return

	files = [f for f in os.listdir(CREDENTIALS_DIR) if f.endswith(".json")]
	if not files:
		p_print(
			"No credentials found, please remove all arguments and try again.",
			Colours.FAIL,
		)
		return

	p_print(f"Checking {len(files)} saved account(s)...", Colours.OKCYAN)
	start = time.monotonic()

	with ThreadPoolExecutor(max_workers=min(20, max(5, len(files)))) as pool:
		futures = [
			pool.submit(_process_one, f, idx, len(files), verbose, prune, max_retries)
			for idx, f in enumerate(files, start=1)
		]
		results = [f.result() for f in futures]

	# Batch write / prune after all results are collected.
	for r in results:
		if r["status"] == "OK" and r["data"]:
			try:
				with open(r["path"], "w", encoding="utf-8") as f:
					json.dump(r["data"], f, indent=2)
			except OSError:
				pass
		elif r["status"] == "FAIL" and r["prune"]:
			try:
				os.remove(r["path"])
				p_print(f"    Pruned {os.path.basename(r['path'])}", Colours.WARNING)
			except OSError as e:
				p_print(f"    Could not prune {r['path']}: {e}", Colours.FAIL)

	# Summary table.
	total = elapsed(start)
	separator("Keepalive summary", Colours.HEADER)
	p_print(f"  {len(results)} accounts in {total}", Colours.OKCYAN)
	oks = sum(1 for r in results if r["status"] == "OK")
	fails = sum(1 for r in results if r["status"] == "FAIL")
	p_print(f"  OK:   {oks}", Colours.OKGREEN)
	p_print(f"  FAIL: {fails}", Colours.FAIL)
