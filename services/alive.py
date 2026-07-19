"""Functions related to the keepalive functionality."""

import os
import json

from mega import Mega
from mega.errors import RequestError

from utilities.etc import p_print, Colours

mega = Mega()


def keepalive(verbose: bool):
	"""Keep the generated accounts alive by logging in."""

	if not os.path.isdir("./credentials"):
		p_print(
			"No credentials found, please remove all arguments and try again.",
			Colours.FAIL,
		)
		return

	files = [f for f in os.listdir("./credentials") if f.endswith(".json")]
	if len(files) == 0:
		p_print(
			"No credentials found, please remove all arguments and try again.",
			Colours.FAIL,
		)
		return

	i = 0
	for file in files:
		path = f"./credentials/{file}"
		try:
			with open(path, "r", encoding="utf-8") as f:
				credentials = json.JSONDecoder().decode(f.read())
		except (json.JSONDecodeError, OSError) as e:
			p_print(f"Skipping unreadable credential file {file}: {e}", Colours.WARNING)
			continue

		email = credentials.get("email")
		password = credentials.get("password")
		if not email or not password:
			p_print(f"Skipping {file}: missing email/password.", Colours.WARNING)
			continue

		i += 1
		try:
			mega.login(email, password)
			# mega.get_quota() returns bytes; convert to GB.
			quota_left = mega.get_quota() / (1024**3)
			p_print(
				f"{i}/{len(files)} Successfully logged into {email}",
				Colours.OKGREEN,
			)
			if verbose:
				p_print(f"    {quota_left:.2f} GB of storage left", Colours.OKGREEN)
		except RequestError:
			p_print(f"{i}/{len(files)} Failed to login to {email}", Colours.FAIL)
		except Exception as e:
			p_print(f"{i}/{len(files)} Error with {email}: {e}", Colours.FAIL)
