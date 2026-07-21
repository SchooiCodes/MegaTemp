"""Email provider abstraction layer.

Defines the base interface that all disposable-email providers must
implement. Currently supported backends: ``mailtm`` (default) and
``guerrillamail`` (no signup required). Adding new providers requires
only a class implementing ``EmailProvider`` and registering it in
``_PROVIDERS``.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from utilities.models import Credentials


@dataclass
class Mailbox:
	"""A logged-in mailbox that can be polled for messages."""

	provider: str = ""
	address: str = ""


class EmailProvider(ABC):
	"""Abstract base for a disposable-email service provider."""

	@abstractmethod
	async def create_account(self) -> Credentials:
		"""Create a new disposable inbox and return its credentials."""
		...

	@abstractmethod
	async def login(self, credentials: Credentials) -> Mailbox:
		"""Log into an existing inbox."""
		...

	@abstractmethod
	async def get_message(self, mailbox: Mailbox) -> object:
		"""Fetch the first unread message, or raise if none available."""
		...

	@property
	@abstractmethod
	def name(self) -> str:
		"""Human-readable provider name (e.g. 'mail.tm')."""
		...


# ---------------------------------------------------------------------------
# Provider registry — add new providers here
# ---------------------------------------------------------------------------
_PROVIDERS: dict[str, type[EmailProvider]] = {}


def register_provider(name: str, cls: type[EmailProvider]) -> None:
	"""Register an email provider class under a short name."""
	_PROVIDERS[name] = cls


def get_provider(name: str) -> EmailProvider | None:
	"""Return an instance of the named provider, or None if unknown."""
	cls = _PROVIDERS.get(name)
	if cls is None:
		return None
	return cls()


def get_provider_names() -> list[str]:
	"""Return sorted list of registered provider names."""
	return sorted(_PROVIDERS.keys())


# ---------------------------------------------------------------------------
# Auto-register built-in providers on import.
# Importing these modules triggers their register_provider() calls.
# ---------------------------------------------------------------------------
import utilities.mailtm_provider  # noqa: F401, E402
import utilities.guerrilla  # noqa: F401, E402
