"""Email provider abstraction layer.

Defines the base interface that all disposable-email providers must
implement. Currently only ``mailtm`` is supported, but the protocol
enables adding new backends (Guerrilla Mail, Temp Mail, etc.) without
modifying browser-automation code.
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
