"""All functions related to working with the config file."""

from dataclasses import asdict, fields
import os
import json
import re
import sys
import tempfile

from utilities.etc import p_print
from utilities.filelock import locked
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

	# Tolerate unknown keys (config written by a newer version, or a typo)
	# instead of crashing the whole app with a TypeError from Config(**data).
	known = {f.name for f in fields(Config)}
	unknown = sorted(set(json_data) - known)
	if unknown:
		p_print(
			f"Config: ignoring unknown key(s): {', '.join(unknown)}",
			Colours.WARNING,
		)
		json_data = {k: v for k, v in json_data.items() if k in known}

	# Validate config values
	_validate_config(json_data)

	# Reconcile any missing keys from a newer version of the config schema.
	# This is a read-only operation: writing here made every read a mutation
	# and broke read-only installs.
	defaults = asdict(Config())
	missing = {k: v for k, v in defaults.items() if k not in json_data}
	if missing:
		json_data.update(missing)

	try:
		return Config(**json_data)
	except TypeError as e:
		p_print(f"Config: invalid value type ({e}); using defaults.", Colours.WARNING)
		return Config()


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


def _safe_filename(email: str) -> str:
	"""Build a filesystem-safe credential filename stem from an email address."""
	local_part = (email or "").split("@", 1)[0] or "account"
	return "".join(c if c.isalnum() or c in "-_." else "_" for c in local_part)


def _plaintext_warning(path: str) -> None:
	"""Warn when an export bypasses at-rest credential encryption."""
	if not _get_encryption_password():
		return
	p_print(
		f"WARNING: {path} is written in PLAINTEXT even though an encryption "
		"password is configured. Delete it after use or use the encrypted "
		"per-account JSON store.",
		Colours.WARNING,
	)


def save_credentials(
	credentials: Credentials, account_format: str, encryption_password: str = ""
) -> None:
	"""Pass credentials into a file.

	When `account_format` is set the credentials are appended to a single
	`accounts.txt` using that template. Otherwise one JSON file per account
	is written. Filenames are derived from the local part of the email
	(`user@domain` -> `user`) so they stay valid regardless of the TLD length.
	"""
	os.makedirs(CREDENTIALS_DIR, exist_ok=True)

	if account_format != "":
		line = (
			account_format.replace("{email}", credentials.email)
			.replace("{password}", credentials.password)
			.replace("{emailPassword}", credentials.emailPassword)
			+ "\n"
		)
		path = os.path.join(CREDENTIALS_DIR, "accounts.txt")
		_plaintext_warning(path)
		try:
			# Appends from parallel/isolated workers must not interleave.
			with locked(path):
				with open(path, "a", encoding="utf-8", newline="") as file:
					file.write(line)
		except OSError as e:
			p_print(f"Failed to write {path}: {e}", Colours.FAIL)
		return

	safe_name = _safe_filename(credentials.email)

	data = asdict(credentials)
	if encryption_password:
		encrypt_credential(data, encryption_password)

	path = os.path.join(CREDENTIALS_DIR, f"{safe_name}.json")
	try:
		with locked(path):
			with open(path, "w", encoding="utf-8", newline="\n") as file:
				file.write(json.dumps(data, indent=2))
		_credentials_cache.pop(path, None)
	except OSError as e:
		p_print(f"Failed to write credentials file: {e}", Colours.FAIL)


def save_credentials_csv(credentials: Credentials) -> None:
	"""Append the credentials to credentials/accounts.csv (email,password,emailPassword)."""
	import csv

	os.makedirs(CREDENTIALS_DIR, exist_ok=True)
	csv_path = os.path.join(CREDENTIALS_DIR, "accounts.csv")
	_plaintext_warning(csv_path)
	try:
		with locked(csv_path):
			write_header = (
				not os.path.exists(csv_path) or os.stat(csv_path).st_size == 0
			)
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
	with open(_config_path(), "w", encoding="utf-8", newline="\n") as f:
		f.write(json.dumps(asdict(config), indent=4, sort_keys=True))
	return config


def save_credentials_jsonl(credentials: Credentials) -> None:
	"""Append credentials as a JSON Line to credentials/accounts.jsonl."""
	os.makedirs(CREDENTIALS_DIR, exist_ok=True)

	path = os.path.join(CREDENTIALS_DIR, "accounts.jsonl")
	_plaintext_warning(path)
	try:
		with locked(path):
			with open(path, "a", encoding="utf-8", newline="\n") as f:
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
					(key * (64 // len(key) + 1))[:64],
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
			dec = bytes(
				a ^ b
				for a, b in zip(
					enc,
					(key * (len(enc) // len(key) + 1))[: len(enc)],
					strict=True,
				)
			)
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


def reset_encryption_password_cache() -> None:
	"""Forget the cached encryption password (tests/config reloads)."""
	global _encryption_password_cache
	_encryption_password_cache = ""


def load_credential_file(path: str, password: str | None = None) -> tuple[dict, bool]:
	"""Return ``(decrypted data, was_encrypted)`` for a credential JSON file.

	Centralises the ENC:/OBS: detection so every reader (exports, extract,
	keepalive, viewer) sees plaintext credentials instead of literal
	``ENC:gAAAA...`` strings.
	"""
	with open(path, "r", encoding="utf-8") as fh:
		data = json.load(fh)
	encrypted = any(
		isinstance(v, str) and v.startswith(("ENC:", "OBS:")) for v in data.values()
	)
	if encrypted:
		key = _get_encryption_password() if password is None else password
		if key:
			decrypt_credential(data, key)
	return data, encrypted


def _data_to_credentials(data: dict) -> Credentials:
	"""Build a Credentials object from a raw/decrypted credential dict."""
	return Credentials(
		email=data.get("email", ""),
		emailPassword=data.get("emailPassword", ""),
		password=data.get("password", ""),
		id=data.get("id", ""),
		notes=data.get("notes", ""),
		tags=data.get("tags", ""),
		lastLogin=float(data.get("lastLogin", 0.0) or 0.0),
	)


def _parse_account_format(account_format: str, line: str) -> Credentials | None:
	"""Reverse the account_format template to extract fields from a line.

	Templates support the {email}, {password} and {emailPassword} placeholders
	(e.g. "{email}#{password}"). Returns None when the line doesn't match.
	"""
	fmt = account_format or "{email}#{password}"
	pattern = "^" + re.escape(fmt)
	names = []
	for name in ("email", "password", "emailPassword"):
		tok = "{" + name + "}"
		if tok in fmt:
			names.append(name)
			pattern = pattern.replace(re.escape(tok), f"(?P<{name}>.*?)")
	pattern += "$"
	match = re.match(pattern, line.rstrip("\n"))
	if not match:
		return None
	return Credentials(
		email=match.group("email") or "",
		emailPassword=match.group("emailPassword") or ""
		if "emailPassword" in names
		else "",
		password=match.group("password") or "",
	)


def read_accounts_txt(account_format: str = "") -> list[tuple[str, Credentials, float]]:
	"""Parse credentials/accounts.txt (the single-file store written by
	save_credentials when accountFormat is set) back into Credentials.

	Returns a list of (basename, Credentials, mtime) tuples.
	"""
	path = os.path.join(CREDENTIALS_DIR, "accounts.txt")
	if not os.path.isfile(path):
		return []
	try:
		mtime = os.path.getmtime(path)
	except OSError:
		mtime = 0.0
	result = []
	with open(path, "r", encoding="utf-8") as fh:
		for line in fh:
			creds = _parse_account_format(account_format, line)
			if creds is None or not creds.email:
				continue
			result.append((creds.email, creds, mtime))
	return result


def remove_accounts_txt_line(email: str, account_format: str = "") -> bool:
	"""Remove every line in credentials/accounts.txt matching *email*."""
	path = os.path.join(CREDENTIALS_DIR, "accounts.txt")
	if not os.path.isfile(path):
		return False
	try:
		with open(path, "r", encoding="utf-8") as fh:
			lines = fh.readlines()
	except OSError:
		return False
	kept = []
	removed = False
	for ln in lines:
		creds = _parse_account_format(account_format, ln)
		if creds is not None and creds.email == email:
			removed = True
			continue
		kept.append(ln)
	if removed:
		try:
			with open(path, "w", encoding="utf-8") as fh:
				fh.writelines(kept)
		except OSError:
			return False
	return removed


def list_credentials() -> list[tuple[str, Credentials, float]]:
	"""Return sorted list of (filename, Credentials, mtime) from credentials/."""
	import glob

	result: list[tuple[str, Credentials, float]] = []
	if not os.path.isdir(CREDENTIALS_DIR):
		return result

	enc_pw = _get_encryption_password()

	for path in sorted(
		glob.glob(os.path.join(CREDENTIALS_DIR, "*.json")),
		key=os.path.getmtime,
		reverse=True,
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
			data = load_credential_file(path, password=enc_pw)[0]
		except (json.JSONDecodeError, OSError):
			continue
		creds = _data_to_credentials(data)
		_credentials_cache[path] = (mtime, creds)
		result.append((os.path.basename(path), creds, mtime))

	# Include flat accounts.txt entries (the store used when accountFormat is
	# set), skipping emails already present as per-account JSON files.
	cfg = read_config()
	_fmt = cfg.accountFormat if cfg else ""
	_known = {c.email for _, c, _ in result}
	for name, creds, mtime in read_accounts_txt(_fmt):
		if creds.email in _known:
			continue
		result.append((name, creds, mtime))
		_known.add(creds.email)
	return result


def find_credential_path(email: str) -> str | None:
	"""Locate the credential store for *email*.

	Handles sanitised JSON filenames (``+``/unicode → ``_``), accounts.txt
	entries and config profiles (the directory constant is shared). Returns
	``None`` when no matching credential exists.
	"""
	email = (email or "").strip()
	if not email:
		return None
	if os.path.isfile(email):
		return email

	for basename, creds, _mtime in list_credentials():
		if (
			creds.email.lower() == email.lower()
			or os.path.splitext(basename)[0] == email
		):
			path = os.path.join(CREDENTIALS_DIR, basename)
			if os.path.isfile(path) and not basename.endswith(".txt"):
				return path
			return os.path.join(CREDENTIALS_DIR, "accounts.txt")

	# Fallback for files that failed to parse (e.g. unknown encryption password).
	candidate = os.path.join(CREDENTIALS_DIR, f"{_safe_filename(email)}.json")
	if os.path.isfile(candidate):
		return candidate
	return None


def _write_json_atomic(path: str, data: dict) -> None:
	"""Write JSON to *path* atomically (temp file + replace)."""
	directory = os.path.dirname(path) or "."
	fd, tmp = tempfile.mkstemp(dir=directory, prefix=".cred-", suffix=".json")
	try:
		with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
			json.dump(data, fh, indent=2)
		os.replace(tmp, path)
	finally:
		if os.path.exists(tmp):
			try:
				os.remove(tmp)
			except OSError:
				pass


def update_credential(email: str, **fields_to_set) -> bool:
	"""Update fields in the stored credential for *email*.

	Decrypts with the configured password, mutates, then re-encrypts. Returns
	False (without touching the file) when an encrypted file cannot be
	decrypted, so a password change can never mangle the store.
	"""
	path = find_credential_path(email)
	if path is None:
		return False
	allowed = {f.name for f in fields(Credentials)}
	updates = {k: v for k, v in fields_to_set.items() if k in allowed}
	if not updates:
		return False

	if os.path.basename(path) == "accounts.txt":
		cfg = read_config()
		fmt = (cfg.accountFormat if cfg else "") or "{email}#{password}"
		path = os.path.join(CREDENTIALS_DIR, "accounts.txt")
		try:
			with open(path, "r", encoding="utf-8") as fh:
				lines = fh.readlines()
		except OSError:
			return False
		changed = False
		for idx, line in enumerate(lines):
			creds = _parse_account_format(fmt, line)
			if creds is None or creds.email.lower() != email.lower():
				continue
			for key, value in updates.items():
				setattr(creds, key, value)
			lines[idx] = (
				fmt.replace("{email}", creds.email)
				.replace("{password}", creds.password)
				.replace("{emailPassword}", creds.emailPassword)
				+ "\n"
			)
			changed = True
		if not changed:
			return False
		try:
			with open(path, "w", encoding="utf-8", newline="\n") as fh:
				fh.writelines(lines)
		except OSError:
			return False
		_invalidate_credentials_cache()
		return True

	try:
		data, was_encrypted = load_credential_file(path)
	except (OSError, json.JSONDecodeError):
		return False
	configured = _get_encryption_password()
	if was_encrypted and not configured:
		p_print(
			f"Cannot update {path}: file is encrypted but no encryption password "
			"is configured.",
			Colours.FAIL,
		)
		return False

	data.update(updates)
	if was_encrypted or configured:
		encrypt_credential(data, configured)
	try:
		_write_json_atomic(path, data)
	except OSError as e:
		p_print(f"Failed to update credentials file: {e}", Colours.FAIL)
		return False
	_credentials_cache.pop(path, None)
	return True


def delete_credential(email: str) -> bool:
	"""Delete the stored credential for *email* (JSON file and/or txt line)."""
	path = find_credential_path(email)
	if path is None:
		return False

	removed = False
	cfg = read_config()
	fmt = (cfg.accountFormat if cfg else "") or ""
	if os.path.basename(path) == "accounts.txt":
		removed = remove_accounts_txt_line(email, fmt)
	else:
		try:
			os.remove(path)
			removed = True
		except OSError:
			removed = False
		# A matching flat-file line may also exist.
		remove_accounts_txt_line(email, fmt)
	_credentials_cache.pop(path, None)
	return removed
