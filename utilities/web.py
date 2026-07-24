"""All functions related to the browser"""

import asyncio
import re
import string
import random
import html
import requests
import pymailtm
from faker import Faker

from pymailtm.pymailtm import CouldNotGetAccountException, CouldNotGetMessagesException
import pyppeteer
import pyppeteer.page

from utilities.etc import (
	Credentials,
	p_print,
	Colours,
	status_line,
	clear_status_line,
)

# Module-level verbosity flag, toggled from main.py via set_verbose().
_VERBOSE = False

# Lazily loaded provider ABC (avoids circular import at module level).
_provider_getter = None


def _get_provider(name: str) -> "EmailProvider":
	global _provider_getter
	if _provider_getter is None:
		from utilities.provider import get_provider as _provider_getter
	return _provider_getter(name)


def set_verbose(value: bool) -> None:
	"""Enable/disable verbose logging across web utilities."""
	global _VERBOSE
	_VERBOSE = value


def _step(text: str, colour: str = Colours.HEADER) -> None:
	"""Always-on phase marker so the user can follow the flow."""
	p_print(text, colour)


def _log(text: str, colour: str = Colours.OKCYAN) -> None:
	"""Verbose-only detail line (only shown with -v)."""
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
	await page.waitForSelector(selector, timeout=8000)
	await page.focus(selector)
	await asyncio.sleep(0.08)
	await page.keyboard.type("x", delay=10)
	await page.evaluate(
		"(_sel) => { const e = document.querySelector(_sel); if (e) e.select(); }",
		selector,
	)
	await page.keyboard.down("Backspace")
	await page.keyboard.up("Backspace")
	await asyncio.sleep(0.03)
	await page.keyboard.type(text, delay=5)
	value = await page.evaluate(
		"(_sel) => document.querySelector(_sel).value", selector
	)
	if value != text:
		raise RuntimeError(
			f"Text did not register in {selector} "
			f"(got {len(value)} chars, expected {len(text)})."
		)
	return value


# Lazy-init Faker instance so we don't load its locale data at module level
# (that adds ~200ms to startup). First call to _get_faker() creates and caches it.
_fake = None


def _get_faker() -> Faker:
	global _fake
	if _fake is None:
		_fake = Faker()
	return _fake


def get_random_string(length: int) -> str:
	"""Generate a random string with a given length."""
	lower_letters = string.ascii_lowercase
	upper_letters = string.ascii_uppercase
	numbers = string.digits
	alphabet = lower_letters + upper_letters + numbers

	return "".join(random.choice(alphabet) for _ in range(length))


async def initial_setup(context: object, message: object, credentials: Credentials) -> None:
	"""Initial setup for the account.

	Opens the MEGA confirmation link, enters the account password to finish
	creating the account, then dismisses the welcome/"free" screen.

	If MEGA has already confirmed the account (modern flow where the link
	redirects directly to the file manager), we skip the password step.
	"""
	confirm_links = re.findall(
		r'href="(https:\/\/mega\.nz\/#confirm[^ ][^"]*)', str(message)
	)
	if not confirm_links:
		raise RuntimeError("No MEGA confirmation link found in the email.")

	# Email bodies are HTML-escaped, so '&' becomes '&amp;' and the link is
	# unusable until we decode it back.
	confirm_link = html.unescape(confirm_links[0])
	_log("[confirm] opening confirmation link ...", Colours.HEADER)
	_log(f"[confirm] link: {confirm_link}")

	confirm_page = await context.newPage()
	try:
		await confirm_page.goto(
			confirm_link, waitUntil="domcontentloaded", timeout=10000
		)

		# MEGA may perform an instant JS redirect from /confirm to /fm/
		# (auto-confirm flow).  domcontentloaded fires before that redirect
		# completes, so the URL may still contain "confirm" at this point.
		# Give MEGA up to 2 s to settle before we decide what flow we're in.
		try:
			await confirm_page.waitForFunction(
				"() => !location.href.includes('confirm')",
				timeout=2000,
			)
		except Exception:
			_log("[confirm] still on confirm page after 2s wait, continuing", Colours.WARNING)

		# Modern MEGA flow: the link may redirect to /fm/ (file manager),
		# meaning the account is already confirmed — no password needed.
		current_url = confirm_page.url
		if "confirm" not in current_url.lower() and "key" not in current_url.lower():
			_step(
				f"[confirm] already confirmed (redirected to {current_url})",
				Colours.OKGREEN,
			)
			await confirm_page.close()
			return

		password_selectors = ["#login-password2", "#confirm-password2", "#password"]
		password_field = None
		for sel in password_selectors:
			try:
				await confirm_page.waitForSelector(sel, timeout=3000)
				password_field = sel
				break
			except Exception:
				continue

		if password_field is None:
			_step("[confirm] confirm page: no password field found", Colours.WARNING)
			# Diagnose what page MEGA actually served — could be a login page,
			# CAPTCHA, phone-verify, or an error page.
			diagnosis = await confirm_page.evaluate(
				"""() => {
					const url = location.href;
					const title = document.title || '';
					const text = (document.body && document.body.innerText) || '';
					const hasCaptcha = /captcha|recaptcha|hcaptcha/i.test(text + title);
					const hasPhone   = /phone|sms|mobile/i.test(text + title);
					const hasLogin   = /log in|sign in|login/i.test(text + title);
					const hasError   = /error|blocked|rate.limit|too.many/i.test(text + title);
					return JSON.stringify({url, title, hasCaptcha, hasPhone, hasLogin, hasError});
				}"""
			)
			raise RuntimeError(
				f"Confirm page password field not found. Page diagnosis: {diagnosis}"
			)

		_log(f"[confirm] typing password into {password_field} ...", Colours.HEADER)
		await _robust_type(confirm_page, password_field, credentials.password)

		# The confirm page's submit button has the text "Confirm". Click the
		# visible one specifically (the login template also has a .login-button).
		_log("[confirm] clicking 'Confirm' ...", Colours.HEADER)
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
					await confirm_page.waitForSelector(sel, timeout=3000)
					await confirm_page.click(sel)
					break
				except Exception:
					continue
			_log("[confirm] used fallback submit selector.")

		# The account is only truly created once MEGA leaves the confirm page.
		# Wait for the URL to change away from "confirm" (success lands on the
		# recovery-key / 2FA screen, "#key") or for an error to surface. If we
		# stay on the confirm page, the password did not match -> raise so the
		# caller retries with a fresh email instead of saving dead credentials.
		_log("[confirm] waiting for account creation ...", Colours.HEADER)
		try:
			await confirm_page.waitForFunction(
				"() => !location.href.includes('confirm')",
				timeout=10000,
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

		_log(
			f"[confirm] account created (final URL: {confirm_page.url})",
			Colours.OKGREEN,
		)

		# Dismiss the recovery-key / 2FA setup screen by clicking "Later" if it
		# is shown, so a brand-new browser session starts at the login screen.
		try:
			await confirm_page.waitForSelector(
				".dialog-download-recovery-key", timeout=1500
			)
			_log("[confirm] dismissing recovery-key prompt ...", Colours.HEADER)
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
	finally:
		# Always close the confirmation tab so incognito pages don't pile up
		# across retries.
		try:
			await confirm_page.close()
		except Exception:
			pass


async def mail_login(credentials: Credentials, provider_name: str = "mailtm") -> object | None:
	"""Log into the email account and return a mailbox object.

	For mail.tm (default): retries with backoff and caches the session
	across retries.  Other providers route through the EmailProvider ABC.
	"""
	global _last_mail_account, _last_mail_password

	if provider_name != "mailtm":
		prov = _get_provider(provider_name)
		if prov is not None:
			return await prov.login(credentials)
		raise ValueError(f"Unknown email provider: {provider_name}")

	if _last_mail_account is not None:
		_log("[mail] reusing cached mail.tm account across retries.", Colours.OKCYAN)
		return _last_mail_account

	max_retries = 5
	for attempt in range(1, max_retries + 1):
		try:
			mail = await asyncio.to_thread(
				pymailtm.Account,
				credentials.id, credentials.email, credentials.emailPassword
			)
			_log(f"[mail] logged into mailbox {credentials.email}", Colours.OKGREEN)
			# Cache for next retry.
			_last_mail_account = mail
			_last_mail_password = credentials.emailPassword
			return mail
		except CouldNotGetAccountException:
			_log(
				f"[mail] login failed, retrying ({attempt}/{max_retries})...",
				Colours.WARNING,
			)
			await asyncio.sleep(min(attempt, 3))

	raise CouldNotGetAccountException(
		"Could not log into the mail.tm account after multiple attempts."
	)


async def get_mail(mail: object, max_attempts: int = 120) -> object:
	"""Get the latest email from the mailbox.

	For mail.tm mailboxes (pymailtm Account objects), uses the existing
	polling loop.  For other providers (Mailbox objects from the ABC),
	delegates to the provider's get_message and retries on LookupError.

	Polling interval: fixed 2s instead of exponential backoff so the
	email is detected as soon as it arrives, not delayed by deep backoff.
	"""
	# If the mailbox has a provider attribute, it's from the ABC.
	if hasattr(mail, "provider"):
		_log("[mail] polling for confirmation email ...", Colours.HEADER)
		prov = _get_provider(mail.provider)
		if prov is not None:
			for _attempt in range(1, max_attempts + 1):
				try:
					return await prov.get_message(mail)
				except LookupError:
					await asyncio.sleep(2)
			raise LookupError("Confirmation email not received after polling.")
		raise ValueError(f"Unknown provider: {mail.provider}")

	# --- mail.tm specific ---
	_log("[mail] polling for MEGA's confirmation email ...", Colours.HEADER)
	for attempt in range(1, max_attempts + 1):
		try:
			messages = await asyncio.to_thread(mail.get_messages)
			message = messages[0]
			clear_status_line()
			_step("[mail] confirmation email received.", Colours.OKGREEN)
			return message
		except (IndexError, CouldNotGetMessagesException):
			# In-place status update instead of spamming one line per poll.
			status_line(
				f"[mail] waiting for confirmation email ({attempt}/{max_attempts})...",
				Colours.WARNING,
			)
			await asyncio.sleep(2)

	clear_status_line()
	raise CouldNotGetMessagesException(
		"Timed out waiting for the confirmation email from MEGA."
	)


async def type_name(page: pyppeteer.page.Page, credentials: Credentials) -> None:
	"""Types name and email into the register fields."""
	firstname = _get_faker().first_name()
	_step("[register] opening mega.nz/register ...", Colours.HEADER)
	await page.goto("https://mega.nz/register", waitUntil="domcontentloaded")

	try:
		await page.waitForSelector("#register-firstname", timeout=10000)
	except Exception:
		# MEGA serves a near-empty shell when it rate-limits / blocks an IP
		# or detects automation: the JS app never mounts the form. Detect
		# that early so we don't burn every retry on a silent timeout.
		html_len = await page.evaluate("() => document.body.innerHTML.length")
		text = await page.evaluate("() => document.body.innerText.slice(0, 200)")
		raise RuntimeError(
			"MEGA registration form did not render. MEGA often serves an empty "
			"page when it rate-limits or blocks an IP/automated browser "
			"(body length "
			f"{html_len}, text={text!r}). Try again later or from a different "
			"network/exit node."
		) from None

	await page.waitForSelector("#register-email", timeout=10000)
	# The firstname field is a plain input; page.type is fine here.
	await page.type("#register-firstname", firstname)
	_log(f"[register] firstname: {firstname}")
	# The email field is also a custom MEGA input that can drop the first
	# character, so type it robustly and verify before submitting.
	await _robust_type(page, "#register-email", credentials.email)
	_log(f"[register] typed email: {credentials.email}")
	_log("[register] name + email filled in.", Colours.OKBLUE)


async def finish_form(page: pyppeteer.page.Page, credentials: Credentials) -> None:
	"""Accepts the terms (if visible) and submits the register form."""
	try:
		await page.waitForSelector(".privacy-check", timeout=3000)
		await page.click(".privacy-check", {"force": True})
		_log("[register] accepted privacy check.")
	except Exception:
		_log("[register] no privacy check shown (skipped).")
	await page.waitForSelector(".register-button", timeout=10000)
	_step("[register] submitting registration form ...", Colours.HEADER)
	await page.click(".register-button")


async def type_password(page: pyppeteer.page.Page, credentials: Credentials) -> None:
	"""Types the password into the password field and accepts terms.

	MEGA's password input uses a custom input handler that drops the first
	keystroke if typing starts immediately after focusing. A shortened value
	makes confirmation fail with "Invalid password" and yields dead accounts,
	so we type through `_robust_type` (which primes, clears and verifies).
	"""
	_step("[register] typing account password ...", Colours.HEADER)
	await _robust_type(page, "#register-password", credentials.password)
	p_print("Registered account successfully!", Colours.OKGREEN)


# Cache the mail.tm domain list so we don't hit /domains on every attempt.
_mailtm_domains: list[str] | None = None

# Reusable mail.tm Account across retries (session persistence).
_last_mail_account: pymailtm.Account | None = None
_last_mail_password: str = ""


async def generate_mail(provider_name: str = "mailtm") -> Credentials:
	"""Generate a disposable inbox and return credentials.

	Provider is selected by ``provider_name`` (default ``mailtm``).
	When using mail.tm, unique addresses with high-entropy suffixes are
	used to avoid HTTP 422 collisions.
	"""
	global _mailtm_domains, _last_mail_account, _last_mail_password

	# Route non-mail.tm providers through the EmailProvider ABC.
	if provider_name != "mailtm":
		_last_mail_account = None
		_last_mail_password = ""

		prov = _get_provider(provider_name)
		if prov is not None:
			return await prov.create_account()
		raise ValueError(f"Unknown email provider: {provider_name}")

	# --- mail.tm specific ---
	if _last_mail_account is None:
		if _mailtm_domains is None:
			_log("[mail] fetching available domains ...", Colours.HEADER)
			try:
				resp = await asyncio.to_thread(
					requests.get,
					"https://api.mail.tm/domains",
					headers={"accept": "application/ld+json"},
					timeout=15,
				)
				resp.raise_for_status()
				_mailtm_domains = [
					d["domain"] for d in resp.json()["hydra:member"]
				]
			except Exception as e:
				raise CouldNotGetAccountException(
					f"Could not fetch mail.tm domains: {e}"
				) from e

	max_retries = 10
	last_error = None
	for attempt in range(1, max_retries + 1):
		try:
			address = _unique_mail_address(_mailtm_domains)
			password = get_random_string(10)
			step_resp = await asyncio.to_thread(
				requests.post,
				"https://api.mail.tm/accounts",
				json={"address": address, "password": password},
				headers={"accept": "application/ld+json"},
				timeout=10,
			)
			if step_resp.status_code not in (200, 201):
				raise CouldNotGetAccountException(
					f"HTTP {step_resp.status_code}"
				)
			response_data = step_resp.json()
			account = pymailtm.Account(
				response_data["id"], response_data["address"], password
			)
			# Prime the cache so mail_login can reuse this account immediately.
			_last_mail_account = account
			_last_mail_password = password
			break
		except CouldNotGetAccountException as e:
			last_error = str(e)
			_log(
				f"[mail] retry {attempt}/{max_retries} ({last_error})...",
				Colours.WARNING,
			)
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
	credentials.password = get_random_string(14)
	credentials.id = account.id_

	_step(f"[mail] generated address: {credentials.email}", Colours.OKBLUE)
	_log(f"[mail] mailbox password: {credentials.emailPassword}")
	return credentials


def _unique_mail_address(domains: list[str]) -> str:
	domain = random.choice(domains)
	return f"mt{get_random_string(12)}@{domain}"
