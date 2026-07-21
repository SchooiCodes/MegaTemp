"""Functions related to the keepalive functionality."""

import os
import json
import time

from mega import Mega
from mega.errors import RequestError

from utilities.etc import p_print, Colours, elapsed


def keepalive(verbose: bool, prune: bool = False, max_retries: int = 3):
	"""Keep the generated accounts alive by logging in.

	Args:
		verbose: Show storage quota per account.
		prune: Delete credential files for accounts that fail login.
		max_retries: Retry attempts per account with exponential backoff.
	"""
	if not os.path.isdir("./credentials"):
		p_print(
			"No credentials found, please remove all arguments and try again.",
			Colours.FAIL,
		)
		return

	files = [f for f in os.listdir("./credentials") if f.endswith(".json")]
	if not files:
		p_print(
			"No credentials found, please remove all arguments and try again.",
			Colours.FAIL,
		)
		return

	p_print(f"Checking {len(files)} saved account(s)...", Colours.OKCYAN)
	mega = Mega()
	results: list[dict] = []
	start = time.monotonic()

	for idx, file in enumerate(files, start=1):
		path = f"./credentials/{file}"
		try:
			with open(path, "r", encoding="utf-8") as f:
				credentials = json.load(f)
		except (json.JSONDecodeError, OSError) as e:
			p_print(f"Skipping unreadable credential file {file}: {e}", Colours.WARNING)
			continue

		email = credentials.get("email")
		password = credentials.get("password")
		if not email or not password:
			p_print(f"Skipping {file}: missing email/password.", Colours.WARNING)
			continue

		# Attempt login with exponential backoff retries.
		status = "FAIL"
		quota_gb = 0.0
		for attempt in range(1, max_retries + 1):
			try:
				mega.login(email, password)
				quota_left = mega.get_quota() / (1024**3)
				quota_gb = quota_left
				status = "OK"
				break
			except RequestError:
				if attempt < max_retries:
					sleep_secs = 2 ** (attempt - 1)
					p_print(
						f"  Retry {attempt}/{max_retries} for {email} in {sleep_secs}s...",
						Colours.WARNING,
					)
					time.sleep(sleep_secs)
			except Exception as e:
				p_print(f"{idx}/{len(files)} Error with {email}: {e}", Colours.FAIL)
				status = "FAIL"
				break

		if status == "OK":
			p_print(f"{idx}/{len(files)} OK  {email}", Colours.OKGREEN)
			if verbose:
				p_print(f"    {quota_gb:.2f} GB left", Colours.OKGREEN)
		else:
			p_print(f"{idx}/{len(files)} FAIL {email}", Colours.FAIL)
			if prune:
				try:
					os.remove(path)
					p_print(f"    Pruned {file}", Colours.WARNING)
				except OSError as e:
					p_print(f"    Could not prune {file}: {e}", Colours.FAIL)

		# Compute age from credential file modification time.
		try:
			age_secs = time.time() - os.path.getmtime(path)
			age_days = age_secs / 86400
			age_str = f"{age_days:.0f}d" if age_days >= 1 else f"{age_secs / 3600:.0f}h"
		except OSError:
			age_str = "?"

		results.append(
			{
				"idx": idx,
				"total": len(files),
				"email": email,
				"status": status,
				"quota": f"{quota_gb:.1f} GB" if quota_gb else "-",
				"age": age_str,
			}
		)

	# Summary table.
	total = elapsed(start)
	separator("Keepalive summary", Colours.HEADER)
	p_print(f"  {len(results)} accounts in {total}", Colours.OKCYAN)
	oks = sum(1 for r in results if r["status"] == "OK")
	fails = sum(1 for r in results if r["status"] == "FAIL")
	p_print(f"  OK:   {oks}", Colours.OKGREEN)
	p_print(f"  FAIL: {fails}", Colours.FAIL)


def separator(title: str = "", colour: str = Colours.HEADER, width: int = 60):
	"""Prints a horizontal rule, optionally with a centered title."""
	if title:
		title = f" {title} "
		pad = max(0, width - len(title))
		left = pad // 2
		right = pad - left
		line = ("─" * left) + title + ("─" * right)
	else:
		line = "─" * width
	print(colour + line + Colours.ENDC)
