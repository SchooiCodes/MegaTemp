"""Guerrilla Mail provider — no signup, no API key, free disposable emails."""

import asyncio
import json
import urllib.request
import urllib.parse

from utilities.provider import EmailProvider, Mailbox, register_provider
from utilities.models import Credentials

_API_BASE = "https://api.guerrillamail.com/ajax.php"


def _gm_call(params: dict) -> dict:
	"""Make a synchronous call to the Guerrilla Mail API."""
	query = urllib.parse.urlencode(params)
	url = f"{_API_BASE}?{query}"
	with urllib.request.urlopen(url, timeout=15) as resp:
		return json.loads(resp.read().decode("utf-8"))


class GuerrillaMailProvider(EmailProvider):
	"""Disposable email via Guerrilla Mail (guerrillamail.com)."""

	@property
	def name(self) -> str:
		return "guerrillamail"

	async def create_account(self) -> Credentials:
		"""Create a new Guerrilla Mail inbox.

		Returns a Credentials object where:
		- email = the full email address
		- emailPassword = the sid_token (needed for session auth)
		"""
		data = await asyncio.to_thread(_gm_call, {"f": "get_email_address"})
		email: str = data.get("email_addr", "")
		sid: str = data.get("sid_token", "")
		return Credentials(email=email, emailPassword=sid, password="")

	async def login(self, credentials: Credentials) -> Mailbox:
		"""Restore an existing Guerrilla Mail session.

		Requires credentials.emailPassword to contain the sid_token.
		"""
		email = credentials.email
		local_part = email.split("@")[0]
		data = await asyncio.to_thread(
			_gm_call,
			{
				"f": "set_email_user",
				"email_user": local_part,
				"sid_token": credentials.emailPassword,
			},
		)
		return Mailbox(
			provider=self.name,
			address=data.get("email_addr", email),
		)

	async def get_message(self, mailbox: Mailbox) -> object:
		"""Fetch the first unread message content.

		Returns a dict with keys: mail_id, mail_from, mail_subject, mail_body.
		Raises LookupError if no unread messages are available.
		"""
		sid = mailbox.address
		data = await asyncio.to_thread(
			_gm_call, {"f": "check_email", "seq": "0", "sid_token": sid}
		)
		emails = data.get("list", [])
		if not emails:
			raise LookupError("No messages")
		# Return the newest message
		msg = emails[0]
		full = await asyncio.to_thread(
			_gm_call,
			{"f": "fetch_email", "email_id": msg["mail_id"], "sid_token": sid},
		)
		return {
			"mail_id": full.get("mail_id"),
			"mail_from": full.get("mail_from"),
			"mail_subject": full.get("mail_subject"),
			"mail_body": full.get("mail_body"),
		}


register_provider("guerrillamail", GuerrillaMailProvider)
