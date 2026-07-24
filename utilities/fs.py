"""All functions related to working with the config file."""

from dataclasses import asdict
import os
import json
import sys

from utilities.etc import p_print
from utilities.models import Colours, Credentials, Config, migrate_config

CONFIG_FILE = "config.json"
CREDENTIALS_DIR = "./credentials"
CREDENTIALS_TXT = "credentials.txt"
_CONFIG_PROFILE: str = ""
_credentials_cache: dict[str, tuple[float, Credentials]] = {}


def _invalidate_credentials_cache() -> None:
	_credentials_cache.clear()


def set_config_profile(profile: str) -> None:
	"""Set the active config profile name. The empty string uses config.json."""
	global _CONFIG_PROFILE
	_CONFIG_PROFILE = profile


def _config_path() -> str:
	"""Return the config file path for the current profile."""
	if _CONFIG_PROFILE:
		return f"config-{_CONFIG_PROFILE}.json"
	return CONFIG_FILE


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

	cfg_path = _config_path()
	if not os.path.exists(cfg_path):
		return None
	with open(cfg_path, "r", encoding="utf-8") as f:
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
			os.replace(cfg_path, f"{cfg_path}.bak")
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

	with open(_config_path(), "w", encoding="utf-8") as f:
		config[k] = v
		f.write(json.dumps(asdict(config), indent=4, sort_keys=True))


def write_default_config() -> Config | None:
	"""
	Writes the default config file.
	"""
	cfg_path = _config_path()
	if os.path.exists(cfg_path) and os.stat(cfg_path).st_size != 0:
		return None

	with open(cfg_path, "w", encoding="utf-8") as f:
		f.write(json.dumps(asdict(Config()), indent=4, sort_keys=True))
		return Config()


def save_credentials(
	credentials: Credentials, account_format: str, encryption_password: str = ""
) -> None:
	"""Pass credentials into a file.

	When `account_format` is set the credentials are appended to a single
	`accounts.txt` using that template. Otherwise one JSON file per account
	is written. Filenames are derived from the local part of the email
	(`user@domain` -> `user`) so they stay valid regardless of the TLD length.
	"""
	os.makedirs("credentials", exist_ok=True)

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

	data = asdict(credentials)
	if encryption_password:
		encrypt_credential(data, encryption_password)

	try:
		with open(f"credentials/{safe_name}.json", "w", encoding="utf-8") as file:
			file.write(json.dumps(data, indent=2))
		_credentials_cache.pop(f"credentials/{safe_name}.json", None)
	except OSError as e:
		p_print(f"Failed to write credentials file: {e}", Colours.FAIL)


def save_credentials_csv(credentials: Credentials) -> None:
	"""Append the credentials to credentials/accounts.csv (email,password,emailPassword)."""
	import csv

	os.makedirs("credentials", exist_ok=True)
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
	with open(_config_path(), "w", encoding="utf-8") as f:
		f.write(json.dumps(asdict(config), indent=4, sort_keys=True))
	return config


def save_credentials_jsonl(credentials: Credentials) -> None:
	"""Append credentials as a JSON Line to credentials/accounts.jsonl."""
	os.makedirs("credentials", exist_ok=True)
	from dataclasses import asdict

	path = "credentials/accounts.jsonl"
	try:
		with open(path, "a", encoding="utf-8") as f:
			f.write(json.dumps(asdict(credentials)) + "\n")
	except OSError as e:
		p_print(f"Failed to write {path}: {e}", Colours.FAIL)


def _encrypt_key(password: str) -> bytes:
	"""Derive a 32-byte AES key from a password using SHA-256."""
	import hashlib
	return hashlib.sha256(password.encode()).digest()


def encrypt_credential(data: dict, password: str) -> dict:
	"""Encrypt credential data fields (email, password) in-place.

	Only fields containing sensitive info are encrypted. Falls back to
	base64 obfuscation if cryptography is not installed, with a warning.
	"""
	if not password:
		return data

	import base64
	fields = ["password", "emailPassword"]

	for f in fields:
		val = data.get(f, "")
		if not val:
			continue
		try:
			from cryptography.fernet import Fernet
			key = base64.urlsafe_b64encode(_encrypt_key(password))
			f_obj = Fernet(key)
			data[f] = "ENC:" + f_obj.encrypt(val.encode()).decode()
		except ImportError:
			# Fallback: simple obfuscation (not real encryption!)
			p_print(
				"Install 'cryptography' for real encryption: pip install cryptography",
				Colours.WARNING,
			)
			key = _encrypt_key(password)
			enc_bytes = bytes(
				a ^ b
				for a, b in zip(
					val.encode().ljust(64, b"\0")[:64],
					key * (64 // len(key) + 1),
					strict=True,
				)
			)
			data[f] = "OBS:" + base64.b64encode(enc_bytes).decode()
	return data


def decrypt_credential(data: dict, password: str) -> dict:
	"""Decrypt credential data fields in-place."""
	if not password:
		return data

	import base64
	fields = ["password", "emailPassword"]

	for f in fields:
		val = data.get(f, "")
		if val.startswith("ENC:"):
			try:
				from cryptography.fernet import Fernet, InvalidToken
				key = base64.urlsafe_b64encode(_encrypt_key(password))
				f_obj = Fernet(key)
				data[f] = f_obj.decrypt(val[4:].encode()).decode()
			except (ImportError, InvalidToken) as e:
				p_print(f"Failed to decrypt field '{f}': {e}", Colours.FAIL)
				data[f] = ""
		elif val.startswith("OBS:"):
			key = _encrypt_key(password)
			enc = base64.b64decode(val[4:])
			dec = bytes(a ^ b for a, b in zip(enc, key * (len(enc) // len(key) + 1), strict=True))
			data[f] = dec.rstrip(b"\0").decode(errors="replace")
	return data


_encryption_password_cache: str = ""

def _get_encryption_password() -> str:
	"""Read encryption password from config (best-effort, cached)."""
	global _encryption_password_cache
	if _encryption_password_cache:
		return _encryption_password_cache
	try:
		cfg = read_config()
		if cfg and cfg.encryptionPassword:
			_encryption_password_cache = cfg.encryptionPassword
			return _encryption_password_cache
	except Exception:
		pass
	return ""


def list_credentials() -> list[tuple[str, Credentials, float]]:
	"""Return sorted list of (filename, Credentials, mtime) from credentials/."""
	import glob

	result: list[tuple[str, Credentials, float]] = []
	if not os.path.isdir("credentials"):
		return result

	enc_pw = _get_encryption_password() if _get_encryption_password() else ""

	for path in sorted(
		glob.glob("credentials/*.json"), key=os.path.getmtime, reverse=True
	):
		try:
			mtime = os.path.getmtime(path)
		except OSError:
			continue
		cached = _credentials_cache.get(path)
		if cached and cached[0] == mtime:
			result.append((os.path.basename(path), cached[1], mtime))
			continue
		try:
			with open(path, "r", encoding="utf-8") as fh:
				data = json.load(fh)
		except (json.JSONDecodeError, OSError):
			continue
		if enc_pw and any(
			v.startswith(("ENC:", "OBS:")) for v in data.values() if isinstance(v, str)
		):
			decrypt_credential(data, enc_pw)
		creds = Credentials(
			email=data.get("email", ""),
			emailPassword=data.get("emailPassword", ""),
			password=data.get("password", ""),
			id=data.get("id", ""),
			notes=data.get("notes", ""),
			tags=data.get("tags", ""),
		)
		_credentials_cache[path] = (mtime, creds)
		result.append((os.path.basename(path), creds, mtime))
	return result
