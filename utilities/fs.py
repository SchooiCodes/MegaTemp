"""All functions related to working with the config file."""

from dataclasses import asdict
import os
import json
import sys

from utilities.etc import p_print
from utilities.models import Colours, Credentials, Config, migrate_config

CONFIG_FILE = "config.json"


def _validate_config(data: dict) -> None:
	"""Warn about config issues (bad paths, suspicious values)."""
	if not data:
		return
	# Warn if executablePath points to a non-existent file
	exec_path = data.get("executablePath", "")
	if exec_path and not os.path.isfile(os.path.expanduser(exec_path)):
		p_print(
			f"Config: executablePath '{exec_path}' not found "
			"(browser auto-detection will be attempted).",
			Colours.WARNING,
		)
	# Warn about improbable maxAttempts values
	attempts = data.get("maxAttempts", 4)
	if not isinstance(attempts, int) or attempts < 1 or attempts > 50:
		p_print(
			"Config: maxAttempts should be between 1 and 50.",
			Colours.WARNING,
		)
	# Warn about unknown proxy format
	proxy = data.get("proxy", "")
	if proxy and not proxy.startswith(
		("http://", "https://", "socks4://", "socks5://")
	):
		p_print(
			"Config: proxy URL may be missing protocol "
			"(expected http://, https://, socks4://, or socks5://).",
			Colours.WARNING,
		)


def read_config() -> Config | None:
	"""
	Reads the config file and returns the contents as a dictionary.
	"""

	if not os.path.exists(CONFIG_FILE):
		return None
	with open(CONFIG_FILE, "r", encoding="utf-8") as f:
		raw = f.read()
	if raw.strip() == "":
		write_default_config()
		return None
	try:
		json_data: dict[str, str] = json.loads(raw)
	except json.JSONDecodeError as e:
		p_print(f"Config file is corrupted ({e}); ignoring it.", Colours.WARNING)
		# Back up the broken file so the user can inspect it, then start fresh.
		try:
			os.replace(CONFIG_FILE, f"{CONFIG_FILE}.bak")
		except OSError:
			pass
		write_default_config()
		return None

	# Migrate from older schema versions.
	json_data = migrate_config(json_data)

	# Validate config values
	_validate_config(json_data)

	# Reconcile any missing keys from a newer version of the config schema.
	defaults = asdict(Config())
	missing = {k: v for k, v in defaults.items() if k not in json_data}
	if missing:
		json_data.update(missing)
		merged = Config(**json_data)
		write_config("executablePath", merged.executablePath, merged)
	else:
		merged = Config(**json_data)

	return merged


def concrete_read_config() -> Config:
	"""
	Reads the config file and returns the contents as a dictionary.
	"""

	config = read_config()
	if config is None:
		p_print("Fatal error while reading config file!", Colours.FAIL)
		sys.exit(1)
	return config


def write_config(k: str, v: str, config: Config) -> None:
	"""
	Writes the config file.
	"""

	if config is None:
		return

	with open(CONFIG_FILE, "w", encoding="utf-8") as f:
		config[k] = v
		f.write(json.dumps(asdict(config), indent=4, sort_keys=True))


def write_default_config() -> Config | None:
	"""
	Writes the default config file.
	"""
	if os.path.exists(CONFIG_FILE) and os.stat(CONFIG_FILE).st_size != 0:
		return None

	with open(CONFIG_FILE, "w", encoding="utf-8") as f:
		f.write(json.dumps(asdict(Config()), indent=4, sort_keys=True))
		return Config()


def save_credentials(credentials: Credentials, account_format: str) -> None:
	"""Pass credentials into a file.

	When `account_format` is set the credentials are appended to a single
	`accounts.txt` using that template. Otherwise one JSON file per account
	is written. Filenames are derived from the local part of the email
	(`user@domain` -> `user`) so they stay valid regardless of the TLD length.
	"""
	if not os.path.exists("credentials"):
		os.mkdir("credentials")

	if account_format != "":
		line = (
			account_format.replace("{email}", credentials.email)
			.replace("{password}", credentials.password)
			.replace("{emailPassword}", credentials.emailPassword)
			+ "\n"
		)
		try:
			with open("credentials/accounts.txt", "a", encoding="utf-8") as file:
				file.write(line)
		except OSError as e:
			p_print(f"Failed to write accounts.txt: {e}", Colours.FAIL)
		return

	# Build a safe filename from the local part of the email address.
	local_part = credentials.email.split("@", 1)[0] if credentials.email else "account"
	safe_name = "".join(c if c.isalnum() or c in "-_." else "_" for c in local_part)

	try:
		with open(f"credentials/{safe_name}.json", "w", encoding="utf-8") as file:
			file.write(json.dumps(asdict(credentials), indent=2))
	except OSError as e:
		p_print(f"Failed to write credentials file: {e}", Colours.FAIL)


def save_credentials_csv(credentials: Credentials) -> None:
	"""Append the credentials to credentials/accounts.csv (email,password,emailPassword)."""
	import csv

	if not os.path.exists("credentials"):
		os.mkdir("credentials")
	csv_path = "credentials/accounts.csv"
	write_header = not os.path.exists(csv_path) or os.stat(csv_path).st_size == 0
	try:
		with open(csv_path, "a", encoding="utf-8", newline="") as file:
			writer = csv.writer(file)
			if write_header:
				writer.writerow(["email", "password", "emailPassword"])
			writer.writerow(
				[credentials.email, credentials.password, credentials.emailPassword]
			)
		p_print(f"Exported credentials to {csv_path}", Colours.OKCYAN)
	except OSError as e:
		p_print(f"Failed to write accounts.csv: {e}", Colours.FAIL)


def merge_config(overrides: dict, config: Config | None = None) -> Config:
	"""Merge key-value overrides into the config and write to disk.

	If config is None it will be read from disk first. Returns the updated Config.
	"""
	if config is None:
		config = read_config()
		if config is None:
			config = write_default_config()
			if config is None:
				config = concrete_read_config()

	for k, v in overrides.items():
		config[k] = v
	with open(CONFIG_FILE, "w", encoding="utf-8") as f:
		f.write(json.dumps(asdict(config), indent=4, sort_keys=True))
	return config


def save_credentials_jsonl(credentials: Credentials) -> None:
	"""Append credentials as a JSON Line to credentials/accounts.jsonl."""
	if not os.path.exists("credentials"):
		os.mkdir("credentials")
	from dataclasses import asdict

	path = "credentials/accounts.jsonl"
	try:
		with open(path, "a", encoding="utf-8") as f:
			f.write(json.dumps(asdict(credentials)) + "\n")
	except OSError as e:
		p_print(f"Failed to write {path}: {e}", Colours.FAIL)


def list_credentials() -> list[tuple[str, Credentials, float]]:
	"""Return sorted list of (filename, Credentials, mtime) from credentials/."""
	import glob

	result: list[tuple[str, Credentials, float]] = []
	if not os.path.isdir("credentials"):
		return result
	for path in sorted(
		glob.glob("credentials/*.json"), key=os.path.getmtime, reverse=True
	):
		try:
			with open(path, "r", encoding="utf-8") as fh:
				data = json.load(fh)
		except (json.JSONDecodeError, OSError):
			continue
		creds = Credentials(
			email=data.get("email", ""),
			emailPassword=data.get("emailPassword", ""),
			password=data.get("password", ""),
			id=data.get("id", ""),
			notes=data.get("notes", ""),
			tags=data.get("tags", ""),
		)
		mtime = os.path.getmtime(path)
		result.append((os.path.basename(path), creds, mtime))
	return result
