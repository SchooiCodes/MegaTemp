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

from utilities.etc import (
	Credentials,
	p_print,
	Colours,
	status_line,
	clear_status_line,
)

# Module-level verbosity flag, toggled from main.py via set_verbose().
_VERBOSE = False


def set_verbose(value: bool) -> None:
	"""Enable/disable verbose logging across web utilities."""
	global _VERBOSE
	_VERBOSE = value


def _step(text, colour=Colours.HEADER):
	"""Always-on phase marker so the user can follow the flow."""
	p_print(text, colour)


def _log(text, colour=Colours.OKCYAN):
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
	await page.waitForSelector(selector)
	await page.focus(selector)
	await asyncio.sleep(0.1)
	await page.keyboard.type("x", delay=10)
	await page.evaluate(
		"(_sel) => { const e = document.querySelector(_sel); if (e) e.select(); }",
		selector,
	)
	await page.keyboard.down("Backspace")
	await page.keyboard.up("Backspace")
	await asyncio.sleep(0.05)
	await page.keyboard.type(text, delay=25)
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
	_step("[confirm] opening confirmation link ...", Colours.HEADER)
	_log(f"[confirm] link: {confirm_link}")

	confirm_page = await context.newPage()
	try:
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

		_step(f"[confirm] typing password into {password_field} ...", Colours.HEADER)
		await _robust_type(confirm_page, password_field, credentials.password)

		# The confirm page's submit button has the text "Confirm". Click the
		# visible one specifically (the login template also has a .login-button).
		_step("[confirm] clicking 'Confirm' ...", Colours.HEADER)
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
			_log("[confirm] used fallback submit selector.")

		# The account is only truly created once MEGA leaves the confirm page.
		# Wait for the URL to change away from "confirm" (success lands on the
		# recovery-key / 2FA screen, "#key") or for an error to surface. If we
		# stay on the confirm page, the password did not match -> raise so the
		# caller retries with a fresh email instead of saving dead credentials.
		_step("[confirm] waiting for account creation ...", Colours.HEADER)
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

		_step(
			f"[confirm] account created (final URL: {confirm_page.url})",
			Colours.OKGREEN,
		)

		# Dismiss the recovery-key / 2FA setup screen by clicking "Later" if it
		# is shown, so a brand-new browser session starts at the login screen.
		try:
			await confirm_page.waitForSelector(
				".dialog-download-recovery-key", timeout=5000
			)
			_step("[confirm] dismissing recovery-key prompt ...", Colours.HEADER)
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


async def mail_login(credentials: Credentials):
	"""Logs into the mail.tm account with the generated credentials.

	Retries a bounded number of times (with backoff) on transient failures
	instead of looping forever. If a mail.tm account with unread messages
	was cached from a previous attempt, it reuses that to avoid burning a
	fresh disposable inbox on every retry.
	"""
	global _last_mail_account, _last_mail_password

	if _last_mail_account is not None:
		_log("[mail] reusing cached mail.tm account across retries.", Colours.OKCYAN)
		return _last_mail_account

	max_retries = 10
	for attempt in range(1, max_retries + 1):
		try:
			mail = pymailtm.Account(
				credentials.id, credentials.email, credentials.emailPassword
			)
			_step(f"[mail] logged into mailbox {credentials.email}", Colours.OKGREEN)
			# Cache for next retry.
			_last_mail_account = mail
			_last_mail_password = credentials.emailPassword
			return mail
		except CouldNotGetAccountException:
			p_print(
				f"[mail] login failed, retrying ({attempt}/{max_retries})...",
				Colours.WARNING,
			)
			await asyncio.sleep(min(attempt, 5))

	raise CouldNotGetAccountException(
		"Could not log into the mail.tm account after multiple attempts."
	)


async def get_mail(mail, max_attempts: int = 120):
	"""Get the latest email from the mail.tm account.

	max_attempts * 1.0s sleep ≈ 2min of polling before giving up.
	"""
	_step("[mail] polling for MEGA's confirmation email ...", Colours.HEADER)
	for attempt in range(1, max_attempts + 1):
		try:
			message = mail.get_messages()[0]
			clear_status_line()
			_step("[mail] confirmation email received.", Colours.OKGREEN)
			return message
		except (IndexError, CouldNotGetMessagesException):
			# In-place status update instead of spamming one line per poll.
			status_line(
				f"[mail] waiting for confirmation email ({attempt}/{max_attempts})...",
				Colours.WARNING,
			)
			await asyncio.sleep(1.0)

	clear_status_line()
	raise CouldNotGetMessagesException(
		"Timed out waiting for the confirmation email from MEGA."
	)


async def type_name(page: pyppeteer.page.Page, credentials: Credentials):
	"""Types name and email into the register fields."""
	firstname = _get_faker().first_name()
	_step("[register] opening mega.nz/register ...", Colours.HEADER)
	await page.goto("https://mega.nz/register")

	try:
		await page.waitForSelector("#register-firstname", timeout=45000)
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

	await page.waitForSelector("#register-email")
	# The firstname field is a plain input; page.type is fine here.
	await page.type("#register-firstname", firstname)
	_log(f"[register] firstname: {firstname}")
	# The email field is also a custom MEGA input that can drop the first
	# character, so type it robustly and verify before submitting.
	await _robust_type(page, "#register-email", credentials.email)
	_log(f"[register] typed email: {credentials.email}")
	_step("[register] name + email filled in.", Colours.OKBLUE)


async def finish_form(page: pyppeteer.page.Page, credentials: Credentials):
	"""Accepts the terms (if visible) and submits the register form."""
	try:
		await page.waitForSelector(".privacy-check", timeout=5000)
		await page.click(".privacy-check", {"force": True})
		_log("[register] accepted privacy check.")
	except Exception:
		_log("[register] no privacy check shown (skipped).")
	await page.waitForSelector(".register-button")
	_step("[register] submitting registration form ...", Colours.HEADER)
	await page.click(".register-button")


async def type_password(page: pyppeteer.page.Page, credentials: Credentials):
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


async def generate_mail() -> Credentials:
	"""Generate mail.tm account and return account credentials.

	mail.tm's API uses random usernames which often collide with existing
	accounts (HTTP 422 "already used"). To avoid excessive retries we
	generate unique addresses ourselves by appending high-entropy random
	suffixes, and we reuse the MailTm client between attempts so the
	domain list is fetched only once.
	"""
	global _mailtm_domains, _last_mail_account, _last_mail_password
	# Reset session cache since we are generating a brand new email.
	_last_mail_account = None
	_last_mail_password = ""

	mail = pymailtm.MailTm()

	# Fetch and cache the domain list across retries (it never changes).
	if _mailtm_domains is None:
		_step("[mail] fetching available domains ...", Colours.HEADER)
		try:
			_mailtm_domains = mail._get_domains_list()
		except Exception as e:
			raise CouldNotGetAccountException(
				f"Could not fetch mail.tm domains: {e}"
			) from e

	# Monkey-patch MailTm so it uses our cached domains.
	mail._get_domains_list = lambda: _mailtm_domains

	max_retries = 20
	last_error = None
	for attempt in range(1, max_retries + 1):
		try:
			address = _unique_mail_address(_mailtm_domains)
			password = get_random_string(10)
			response = mail._make_account_request("accounts", address, password)
			account = pymailtm.Account(response["id"], response["address"], password)
			mail._save_account(account)
			break
		except CouldNotGetAccountException as e:
			last_error = str(e)
			_step(
				f"[mail] retry {attempt}/{max_retries} ({last_error})...",
				Colours.WARNING,
			)
			# With unique addresses the hit rate is ~95 % on the first try,
			# so a quick jittered backoff is all we need for the rare
			# collision retry.
			await asyncio.sleep(0.3 + (attempt % 5) * 0.25)
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
	"""Build a mail.tm address with a unique-enough local part.

	The random_username library (used by pymailtm internally) generates
	common words like 'pleasedpepper' that collide often. We instead
	generate a unique address using high-entropy random characters with
	a human-friendly prefix, drastically reducing the chance of hitting
	HTTP 422 "already used".
	"""
	local = f"mt{get_random_string(12)}"
	domain = random.choice(domains)
	return f"{local}@{domain}"
