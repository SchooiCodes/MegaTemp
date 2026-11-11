import os
import csv
import json
from utilities.etc import p_print, Colours

from utilities.fs import (
	CREDENTIALS_DIR as CREDENTIALS_FOLDER,
	CREDENTIALS_TXT as OUTPUT_FILE,
	load_credential_file,
)


def _load_all() -> list[dict]:
	"""Load and decrypt all credential JSON files from the credentials folder."""
	if not os.path.isdir(CREDENTIALS_FOLDER):
		return []
	results = []
	for f in sorted(os.listdir(CREDENTIALS_FOLDER)):
		if not f.endswith(".json"):
			continue
		path = os.path.join(CREDENTIALS_FOLDER, f)
		try:
			data, _encrypted = load_credential_file(path)
			results.append(data)
		except (json.JSONDecodeError, OSError):
			continue
	return results


_EXPORT_FORMATS = {
	"bitwarden": {
		"file": "bitwarden_export.csv",
		"header": [
			"folder",
			"favorite",
			"type",
			"name",
			"notes",
			"login_uri",
			"login_username",
			"login_password",
			"login_totp",
		],
		"row": lambda a: [
			"",
			"0",
			"1",
			a.get("email", ""),
			a.get("notes", ""),
			"https://mega.nz",
			a.get("email", ""),
			a.get("password", ""),
			"",
		],
	},
	"1password": {
		"file": "1password_export.csv",
		"header": ["title", "url", "username", "password", "notes"],
		"row": lambda a: [
			f"MEGA - {a.get('email', '')}",
			"https://mega.nz",
			a.get("email", ""),
			a.get("password", ""),
			a.get("notes", ""),
		],
	},
	"keepass": {
		"file": "keepass_export.csv",
		"header": ["Group", "Title", "Username", "Password", "URL", "Notes"],
		"row": lambda a: [
			"MEGA",
			a.get("email", ""),
			a.get("email", ""),
			a.get("password", ""),
			"https://mega.nz",
			a.get("notes", ""),
		],
	},
}


def _export_csv(fmt: str) -> str:
	cfg = _EXPORT_FORMATS.get(fmt)
	if not cfg:
		raise ValueError(f"unknown export format: {fmt}")
	accounts = _load_all()
	os.makedirs(CREDENTIALS_FOLDER, exist_ok=True)
	output_path = os.path.join(CREDENTIALS_FOLDER, cfg["file"])
	with open(output_path, "w", encoding="utf-8", newline="") as f:
		w = csv.writer(f)
		w.writerow(cfg["header"])
		for a in accounts:
			w.writerow(cfg["row"](a))
			p_print(f"  + {a.get('email', '?')}", Colours.OKCYAN)
	p_print(f"{fmt.capitalize()} CSV saved to {output_path}", Colours.OKGREEN)
	return output_path


def export_bitwarden_csv() -> str:
	return _export_csv("bitwarden")


def export_onepassword_csv() -> str:
	return _export_csv("1password")


def export_keepass_csv() -> str:
	return _export_csv("keepass")


def extract_credentials(account_format: str = "{email}#{password}") -> None:
	# An empty format (the default in config.json) means "use the default
	# text template" rather than writing blank lines, mirroring the JSON
	# per-account default used by save_credentials.
	if not account_format:
		account_format = "{email}#{password}"

	if not os.path.isdir(CREDENTIALS_FOLDER):
		p_print("No credentials folder found, nothing to extract.", Colours.FAIL)
		return

	json_files = [
		f
		for f in os.listdir(CREDENTIALS_FOLDER)
		if f.endswith(".json") and os.path.isfile(os.path.join(CREDENTIALS_FOLDER, f))
	]
	p_print(f"Extracting {len(json_files)} account(s)...", Colours.OKCYAN)

	with open(OUTPUT_FILE, "w", encoding="utf-8", newline="\n") as output_file:
		for file in json_files:
			file_path = os.path.join(CREDENTIALS_FOLDER, file)

			try:
				data, was_encrypted = load_credential_file(file_path)
			except (json.JSONDecodeError, OSError):
				p_print(
					f"Failed to parse JSON file: {file}, skipping...",
					Colours.WARNING,
				)
				continue

			password = data.get("password", "")
			emailPassword = data.get("emailPassword", "")
			if was_encrypted and any(
				str(v).startswith(("ENC:", "OBS:")) for v in (password, emailPassword)
			):
				p_print(
					f"Cannot decrypt {file} (no/wrong encryption password), skipping...",
					Colours.WARNING,
				)
				continue

			email = data.get("email", "")

			# Replace placeholders in the account_format string with actual values
			output = (
				account_format.replace("{email}", email)
				.replace("{password}", password)
				.replace("{emailPassword}", emailPassword)
			)

			output_file.write(f"{output}\n")
			p_print(f"  + {email}", Colours.OKCYAN)

	p_print("Data extraction and writing complete!", Colours.OKGREEN)
	p_print(f"Output saved to: {os.path.abspath(OUTPUT_FILE)}", Colours.OKGREEN)
