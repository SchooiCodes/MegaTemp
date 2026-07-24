"""mail.tm email provider — wraps pymailtm into the EmailProvider ABC."""

import asyncio
import random
import pymailtm
from pymailtm.pymailtm import CouldNotGetAccountException

from utilities.provider import EmailProvider, Mailbox, register_provider
from utilities.models import Credentials
from utilities.etc import p_print, Colours

_VERBOSE = False


def set_verbose(value: bool) -> None:
	global _VERBOSE
	_VERBOSE = value


def _step(text, colour=Colours.HEADER):
	p_print(text, colour)


def _log(text, colour=Colours.OKCYAN):
	if _VERBOSE:
		p_print(text, colour)


class MailTmProvider(EmailProvider):
	"""Email provider backed by mail.tm (via pymailtm)."""

	_mailtm_domains: list[str] | None = None

	@property
	def name(self) -> str:
		return "mailtm"

	async def create_account(self) -> Credentials:
		"""Create a new mail.tm inbox."""
		mail = pymailtm.MailTm()

		if self._mailtm_domains is None:
			_step("[mail] fetching available domains ...", Colours.HEADER)
			try:
				self.__class__._mailtm_domains = await asyncio.to_thread(
					mail._get_domains_list
				)
			except Exception as e:
				raise CouldNotGetAccountException(
					f"Could not fetch mail.tm domains: {e}"
				) from e

		mail._get_domains_list = lambda: self._mailtm_domains

		max_retries = 10
		last_error = None
		for attempt in range(1, max_retries + 1):
			try:
				from utilities.web import _unique_mail_address, get_random_string
				address = _unique_mail_address(self._mailtm_domains)
				password = get_random_string(10)
				response = await asyncio.to_thread(
					mail._make_account_request, "accounts", address, password
				)
				account = pymailtm.Account(
					response["id"], response["address"], password
				)
				mail._save_account(account)
				break
			except CouldNotGetAccountException as e:
				last_error = str(e)
				_step(
					f"[mail] retry {attempt}/{max_retries} ({last_error})...",
					Colours.WARNING,
				)
				# HTTP 429 (rate limiting) — exponential backoff with jitter.
				# Address collisions — short jittered wait is sufficient.
				if "429" in last_error or "Too Many" in last_error:
					delay = min(2 ** (attempt - 1) + random.uniform(0, 1), 10)
				else:
					delay = 0.3 + (attempt % 5) * 0.25
				await asyncio.sleep(delay)
		else:
			raise CouldNotGetAccountException(
				f"Could not create a mail.tm account after {max_retries} attempts "
				f"(last error: {last_error}). "
				"mail.tm may be down or rate-limiting."
			)

		credentials = Credentials()
		credentials.email = account.address
		credentials.emailPassword = account.password
		from utilities.web import get_random_string
		credentials.password = get_random_string(14)
		credentials.id = account.id_
		return credentials

	async def login(self, credentials: Credentials) -> Mailbox:
		"""Log into an existing mail.tm inbox."""
		mail = pymailtm.MailTm()
		account = await asyncio.to_thread(
			mail.login, credentials.email, credentials.emailPassword
		)
		return Mailbox(provider=self.name, address=account.id_)

	async def get_message(self, mailbox: Mailbox) -> object:
		"""Fetch the first unread message, or raise."""
		mail = pymailtm.MailTm()
		account = await asyncio.to_thread(mail.login, mailbox.address, "")
		message = await asyncio.to_thread(account.get_message)
		if message is None:
			raise LookupError("No messages")
		return {
			"mail_id": message.id,
			"mail_from": message.from_,
			"mail_subject": message.subject,
			"mail_body": message.body,
		}


register_provider("mailtm", MailTmProvider)
