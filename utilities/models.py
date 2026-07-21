from dataclasses import dataclass


@dataclass
class Colours:
	"""Colours for the console."""

	HEADER: str = "\033[95m"
	OKBLUE: str = "\033[94m"
	OKCYAN: str = "\033[96m"
	OKGREEN: str = "\033[92m"
	WARNING: str = "\033[93m"
	FAIL: str = "\033[91m"
	ENDC: str = "\033[0m"


@dataclass
class Credentials:
	"""Credentials for the account."""

	email: str = ""
	emailPassword: str = ""
	password: str = ""
	id: str = ""


@dataclass
class Config:
	"""Config class."""

	schemaVersion: int = 1
	executablePath: str = ""
	accountFormat: str = ""
	proxy: str = ""
	proxyFile: str = ""
	proxyPerAttempt: bool = False
	maxAttempts: int = 4
	csvExport: bool = False
	visibleBrowser: bool = False
	emailProvider: str = "mailtm"

	def __getitem__(self, key):
		return self.__dict__[key]

	def __setitem__(self, key, value):
		self.__dict__[key] = value


# Schema migration table: keyed by source version, value is a callable
# that transforms the raw dict in-place and bumps schemaVersion.
_CONFIG_MIGRATIONS: dict[int, callable] = {
	0: lambda d: d.update(
		{
			"schemaVersion": 1,
			"proxy": "",
			"proxyFile": "",
			"proxyPerAttempt": False,
			"maxAttempts": 4,
			"csvExport": False,
			"visibleBrowser": False,
			"emailProvider": "mailtm",
		}
	),
}


def migrate_config(raw: dict) -> dict:
	"""Migrate a raw config dict from any older schema version to the latest."""
	while raw.get("schemaVersion", 0) < Config().schemaVersion:
		ver = raw.get("schemaVersion", 0)
		migrator = _CONFIG_MIGRATIONS.get(ver)
		if migrator is None:
			raise RuntimeError(f"No migration path from config schema version {ver}")
		migrator(raw)
	return raw
