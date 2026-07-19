"""All functions related to the browser"""

import asyncio
import re
import string
import random
import html
import pymailtm
from faker import Faker

from pymailtm.pymailtm import CouldNotGetAccountException, CouldNotGetMessagesException
import pyppeteer
import pyppeteer.page

from utilities.etc import Credentials, p_print, Colours

# Module-level verbosity flag, toggled from main.py via set_verbose().
_VERBOSE = False


def set_verbose(value: bool) -> None:
	"""Enable/disable verbose logging across web utilities."""
	global _VERBOSE
	_VERBOSE = value


def _log(text, colour=Colours.OKCYAN):
	if _VERBOSE:
		p_print(text, colour)


async def _robust_type(page, selector: str, text: str):
	"""Type text into a field reliably.

	MEGA's custom input handlers drop the first keystroke if typing starts
	immediately after focusing, which silently shortens the value. To avoid
	that we: focus, type a throwaway character, select+delete it, then type
	the real text with a small per-character delay, and finally verify the
	field holds exactly what we intended.

	The selector is passed to page.evaluate as an argument (not interpolated
	into the JS string) so that any quoting in a selector cannot break it.
	"""
	await page.waitForSelector(selector)
	await page.focus(selector)
	await asyncio.sleep(0.3)
	await page.keyboard.type("x", delay=30)
	await page.evaluate(
		"(_sel) => { const e = document.querySelector(_sel); if (e) e.select(); }",
		selector,
	)
	await page.keyboard.down("Backspace")
	await page.keyboard.up("Backspace")
	await asyncio.sleep(0.2)
	await page.keyboard.type(text, delay=50)
	value = await page.evaluate(
		"(_sel) => document.querySelector(_sel).value", selector
	)
	if value != text:
		raise RuntimeError(
			f"Text did not register in {selector} "
			f"(got {len(value)} chars, expected {len(text)})."
		)
	return value


fake = Faker()


def get_random_string(length):
	"""Generate a random string with a given length."""
	lower_letters = string.ascii_lowercase
	upper_letters = string.ascii_uppercase
	numbers = string.digits
	alphabet = lower_letters + upper_letters + numbers

	return "".join(random.choice(alphabet) for _ in range(length))


async def initial_setup(context, message, credentials):
	"""Initial setup for the account.

	Opens the MEGA confirmation link, enters the account password to finish
	creating the account, then dismisses the welcome/"free" screen.

	MEGA's SPA selectors change over time, so we try several known selectors
	and fall back to dumping the page DOM if nothing matches.
	"""
	confirm_links = re.findall(
		r'href="(https:\/\/mega\.nz\/#confirm[^ ][^"]*)', str(message)
	)
	if not confirm_links:
		raise RuntimeError("No MEGA confirmation link found in the email.")

	# Email bodies are HTML-escaped, so '&' becomes '&amp;' and the link is
	# unusable until we decode it back.
	confirm_link = html.unescape(confirm_links[0])
	_log(f"Confirmation link: {confirm_link}")

	confirm_page = await context.newPage()
	await confirm_page.goto(confirm_link)

	password_selectors = ["#login-password2", "#confirm-password2", "#password"]
	password_field = None
	for sel in password_selectors:
		try:
			await confirm_page.waitForSelector(sel, timeout=10000)
			password_field = sel
			break
		except Exception:
			continue

	if password_field is None:
		dom = await confirm_page.content()
		p_print(
			"Could not find a password field on the confirm page. Dumping DOM.",
			Colours.WARNING,
		)
		p_print(dom[:2000], Colours.WARNING)
		raise RuntimeError("Confirm page password field not found.")

	await _robust_type(confirm_page, password_field, credentials.password)

	# The confirm page's submit button has the text "Confirm". Click the
	# visible one specifically (the login template also has a .login-button).
	clicked = await confirm_page.evaluate(
		"""() => {
			const btns = Array.from(document.querySelectorAll('button'));
			const b = btns.find(
				x => x.innerText.trim() === 'Confirm' && x.offsetParent !== null
			);
			if (b) { b.click(); return true; }
			return false;
		}"""
	)
	if not clicked:
		submit_selectors = [".login-button", ".register-button", "#login-button2"]
		for sel in submit_selectors:
			try:
				await confirm_page.waitForSelector(sel, timeout=10000)
				await confirm_page.click(sel)
				break
			except Exception:
				continue

	# The account is only truly created once MEGA leaves the confirm page.
	# Wait for the URL to change away from "confirm" (success lands on the
	# recovery-key / 2FA screen, "#key") or for an error to surface. If we
	# stay on the confirm page, the password did not match -> raise so the
	# caller retries with a fresh email instead of saving dead credentials.
	try:
		await confirm_page.waitForFunction(
			"() => !location.href.includes('confirm')",
			timeout=30000,
		)
	except Exception:
		# Still on the confirm page after 30s: surface any visible error text.
		errors = await confirm_page.evaluate(
			"""() => Array.from(
				document.querySelectorAll('.error,.warning,.msg,.input-error,.toast,.notification')
			).map(e => e.innerText.trim()).filter(Boolean)"""
		)
		raise RuntimeError(
			"Account confirmation did not complete (still on confirm page). "
			f"Visible errors: {errors}"
		) from None

	# Dismiss the recovery-key / 2FA setup screen by clicking "Later" if it
	# is shown, so a brand-new browser session starts at the login screen.
	try:
		await confirm_page.waitForSelector(
			".dialog-download-recovery-key", timeout=5000
		)
		await confirm_page.evaluate(
			"""() => {
				const b = Array.from(document.querySelectorAll('button')).find(
					x => /later|skip/i.test(x.innerText) && x.offsetParent !== null
				);
				if (b) b.click();
			}"""
		)
	except Exception:
		pass


async def mail_login(credentials: Credentials):
	"""Logs into the mail.tm account with the generated credentials.

	Retries a bounded number of times (with backoff) on transient failures
	instead of looping forever.
	"""
	max_retries = 10
	for attempt in range(1, max_retries + 1):
		try:
			mail = pymailtm.Account(
				credentials.id, credentials.email, credentials.emailPassword
			)
			p_print("Retrieved mail successfully!", Colours.OKGREEN)
			return mail
		except CouldNotGetAccountException:
			p_print(
				f"Mail login failed, retrying ({attempt}/{max_retries})...",
				Colours.WARNING,
			)
			await asyncio.sleep(min(attempt, 5))

	raise CouldNotGetAccountException(
		"Could not log into the mail.tm account after multiple attempts."
	)


async def get_mail(mail, max_attempts: int = 80):
	"""Get the latest email from the mail.tm account.

	max_attempts * 1.5s sleep ≈ 90s of polling before giving up.
	"""
	for attempt in range(1, max_attempts + 1):
		try:
			message = mail.get_messages()[0]
			p_print("Found mail!", Colours.OKGREEN)
			return message
		except (IndexError, CouldNotGetMessagesException):
			p_print(
				f"Failed to find mail... trying again ({attempt}/{max_attempts}).",
				Colours.WARNING,
			)
			await asyncio.sleep(1.5)

	raise CouldNotGetMessagesException(
		"Timed out waiting for the confirmation email from MEGA."
	)


async def type_name(page: pyppeteer.page.Page, credentials: Credentials):
	"""Types name and email into the register fields."""
	name = str(fake.name()).split(" ", 2)
	firstname = name[0]
	await page.goto("https://mega.nz/register")
	await page.waitForSelector("#register-firstname")
	await page.waitForSelector("#register-email")
	# The firstname field is a plain input; page.type is fine here.
	await page.type("#register-firstname", firstname)
	# The email field is also a custom MEGA input that can drop the first
	# character, so type it robustly and verify before submitting.
	await _robust_type(page, "#register-email", credentials.email)
	_log(f"Registered with email: {credentials.email}")


async def finish_form(page: pyppeteer.page.Page, credentials: Credentials):
	"""Accepts the terms (if visible) and submits the register form."""
	try:
		await page.waitForSelector(".privacy-check", timeout=5000)
		await page.click(".privacy-check", {"force": True})
	except Exception:
		pass
	await page.waitForSelector(".register-button")
	await page.click(".register-button")


async def type_password(page: pyppeteer.page.Page, credentials: Credentials):
	"""Types the password into the password field and accepts terms.

	MEGA's password input uses a custom input handler that drops the first
	keystroke if typing starts immediately after focusing. A shortened value
	makes confirmation fail with "Invalid password" and yields dead accounts,
	so we type through `_robust_type` (which primes, clears and verifies).
	"""
	await _robust_type(page, "#register-password", credentials.password)
	p_print("Registered account successfully!", Colours.OKGREEN)


async def generate_mail() -> Credentials:
	"""Generate mail.tm account and return account credentials."""
	mail = pymailtm.MailTm()
	try_count = 0

	while True:
		try:
			account = mail.get_account()
			break
		except CouldNotGetAccountException:
			p_print("Retrying mail.tm account generation...", Colours.WARNING)
			try_count += 1
			await asyncio.sleep(try_count)

	credentials = Credentials()
	credentials.email = account.address
	credentials.emailPassword = account.password
	credentials.password = get_random_string(14)
	credentials.id = account.id_
	return credentials
