"""Functions related to the keepalive functionality."""

import os
import json
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import utilities.compat  # noqa: F401 — restores asyncio.coroutine for tenacity

from mega import Mega
from mega.errors import RequestError

from utilities.etc import p_print, Colours, elapsed, separator
from utilities.fs import (
	CREDENTIALS_DIR,
	encrypt_credential,
	load_credential_file,
	_get_encryption_password,
)

# Definitive authentication failures. Transient errors (-3 EAGAIN, -4
# ERATELIMIT, network failures) must never cause a credential to be pruned.
_AUTH_ERROR_CODES = {-9, -15, -16}


def _is_auth_failure(exc: Exception) -> bool:
	code = getattr(exc, "code", None)
	return isinstance(code, int) and code in _AUTH_ERROR_CODES


def _is_undecryptable(data: dict) -> bool:
	return any(
		isinstance(v, str) and v.startswith(("ENC2:", "ENC:", "OBS:"))
		for v in data.values()
	)


def _process_one(
	file: str, idx: int, total: int, verbose: bool, prune: bool, max_retries: int
) -> dict:
	"""Process a single credential file for keepalive (runs in a thread)."""
	path = os.path.join(CREDENTIALS_DIR, file)
	result = {
		"idx": idx,
		"total": total,
		"email": "",
		"status": "FAIL",
		"quota": "-",
		"age": "?",
		"path": path,
		"prune": prune,
		"encrypted": False,
		"decrypt_failed": False,
		"auth_failure": False,
		"data": None,
	}
	try:
		data, was_encrypted = load_credential_file(path)
	except (json.JSONDecodeError, OSError) as e:
		p_print(f"Skipping unreadable credential file {file}: {e}", Colours.WARNING)
		return result

	result["encrypted"] = was_encrypted
	if was_encrypted and _is_undecryptable(data):
		# Never treat "we could not decrypt" as "the account is dead".
		result["decrypt_failed"] = True
		p_print(
			f"Skipping {file}: cannot decrypt (configure the encryption password); "
			"prune disabled for this file.",
			Colours.WARNING,
		)
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
		except RequestError as e:
			result["auth_failure"] = _is_auth_failure(e)
			if result["auth_failure"]:
				# Bad credentials/blocked account: retrying cannot help.
				break
			if attempt < max_retries:
				sleep_secs = attempt * 0.5
				p_print(
					f"  Retry {attempt}/{max_retries} for {email} in {sleep_secs}s...",
					Colours.WARNING,
				)
				time.sleep(sleep_secs)
		except (json.JSONDecodeError, OSError):
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


def _backup_and_remove(path: str) -> str | None:
	"""Copy *path* to credentials/pruned/, then remove the original."""
	pruned_dir = os.path.join(CREDENTIALS_DIR, "pruned")
	os.makedirs(pruned_dir, exist_ok=True)
	stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
	base = os.path.basename(path)
	stem, ext = os.path.splitext(base)
	backup = os.path.join(pruned_dir, f"{stem}.{stamp}{ext}")
	counter = 1
	while os.path.exists(backup):
		backup = os.path.join(pruned_dir, f"{stem}.{stamp}-{counter}{ext}")
		counter += 1
	shutil.copy2(path, backup)
	os.remove(path)
	return backup


def keepalive(
	verbose: bool,
	prune: bool = False,
	max_retries: int = 3,
	assume_yes: bool = False,
	workers: int = 0,
) -> None:
	"""Keep the generated accounts alive by logging in.

	Args:
		verbose: Show storage quota per account.
		prune: Back up and remove credential files for accounts that fail
			with a definitive authentication error.
		max_retries: Retry attempts per account with exponential backoff.
		assume_yes: Skip the interactive prune confirmation (--yes).
		workers: Max parallel logins (0 = min(4, account count)).
	"""
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

	# Cap parallel logins: MEGA answers 20 concurrent logins with -4 (rate
	# limit), which used to mark healthy accounts as dead.
	max_workers = workers if workers > 0 else min(4, max(1, len(files)))
	with ThreadPoolExecutor(max_workers=max_workers) as pool:
		futures = [
			pool.submit(_process_one, f, idx, len(files), verbose, prune, max_retries)
			for idx, f in enumerate(files, start=1)
		]
		results = [f.result() for f in futures]

	# Only definitive auth failures on decryptable, unencrypted-safe files are
	# prune candidates. Everything else is left untouched.
	prunable = [
		r
		for r in results
		if r["status"] == "FAIL"
		and r["prune"]
		and r["auth_failure"]
		and not r["decrypt_failed"]
		and not r["encrypted"]
	]
	encrypted_failures = [
		r for r in results if r["status"] == "FAIL" and r["encrypted"]
	]
	if encrypted_failures and prune:
		p_print(
			f"Refusing to prune {len(encrypted_failures)} encrypted credential(s); "
			"remove them manually after verifying the encryption password.",
			Colours.WARNING,
		)

	if prunable and not assume_yes:
		if not (sys.stdin and sys.stdin.isatty()):
			p_print(
				f"Refusing to prune {len(prunable)} account(s) non-interactively. "
				"Re-run with --yes to confirm.",
				Colours.WARNING,
			)
			prunable = []
		else:
			from utilities.menu import prompt_yes_no

			names = ", ".join(r["email"] for r in prunable[:5])
			more = "" if len(prunable) <= 5 else f" (+{len(prunable) - 5} more)"
			if not prompt_yes_no(
				f"Back up and remove {len(prunable)} dead account(s): {names}{more}?",
				default_no=True,
			):
				p_print("Prune cancelled; no files were removed.", Colours.WARNING)
				prunable = []

	# Batch write / prune after all results are collected.
	for r in results:
		if r["status"] == "OK" and r["data"]:
			data = r["data"]
			pw = _get_encryption_password()
			if r["encrypted"] or pw:
				data = encrypt_credential(data, pw)
			try:
				with open(r["path"], "w", encoding="utf-8", newline="\n") as f:
					json.dump(data, f, indent=2)
			except OSError:
				pass
		elif r in prunable:
			try:
				backup = _backup_and_remove(r["path"])
				p_print(
					f"    Pruned {os.path.basename(r['path'])} (backup: {backup})",
					Colours.WARNING,
				)
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
