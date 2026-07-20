"""Main file for the project, handles the arguments and calls the other files."""

import asyncio
import argparse
import os
import sys
from typing import Tuple
import pyppeteer

from services.alive import keepalive
from services.upload import upload_file
from services.extract import extract_credentials
from utilities.fs import (
	Config,
	concrete_read_config,
	read_config,
	write_config,
	write_default_config,
	save_credentials,
)
from utilities.web import (
	finish_form,
	generate_mail,
	type_name,
	type_password,
	initial_setup,
	mail_login,
	get_mail,
	set_verbose,
)
from pymailtm.pymailtm import CouldNotGetMessagesException
from utilities.etc import (
	Credentials,
	p_print,
	clear_console,
	Colours,
	clear_tmp,
	reinstall_tenacity,
	check_for_updates,
	delete_default,
)

# Spooky import to check if the correct version of tenacity is installed.
if sys.version_info.major == 3 and sys.version_info.minor <= 11:
	try:
		pass
	except AttributeError:
		reinstall_tenacity()


# Harmless pyppeteer teardown noise: after we close the browser, pyppeteer's
# connection may still have in-flight CDP messages whose futures resolve with a
# NetworkError ("Target closed." / "No session with given id"). asyncio's GC
# then logs them as "Future exception was never retrieved". These are not real
# errors, so we swallow exactly those while letting anything else through.
_HARMLESS_ASYNC_ERRORS = ("Target closed", "No session with given id")


def _quiet_async_exceptions(loop, context):
	"""asyncio exception handler that hides benign pyppeteer teardown errors.

	"Future exception was never retrieved" GC messages carry the real error
	inside context["future"], not context["exception"], so we inspect the
	future's own exception as well before deciding to suppress.
	"""
	exception = context.get("exception")
	message = context.get("message", "")

	future = context.get("future")
	future_exc = None
	if future is not None:
		try:
			future_exc = future.exception()
		except Exception:
			future_exc = None

	text = f"{exception} {message} {future_exc}"
	if any(marker in text for marker in _HARMLESS_ASYNC_ERRORS):
		return
	loop.default_exception_handler(context)

default_installs = [
	"C:/Program Files/Google/Chrome/Application/chrome.exe",
	"C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
	"C:/Program Files/BraveSoftware/Brave-Browser/Application/brave.exe",
	"C:/Program Files (x86)/BraveSoftware/Brave-Browser/Application/brave.exe",
	"C:/Program Files/Microsoft/Edge/Application/msedge.exe",
]
args = [
	"--no-sandbox",
	"--disable-setuid-sandbox",
	"--disable-gpu",
	"--disable-dev-shm-usage",
	"--disable-infobars",
	"--window-position=0,0",
	"--ignore-certificate-errors",
	"--ignore-certificate-errors-spki-list",
	'--user-agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0"',
]

parser = argparse.ArgumentParser()
parser.add_argument(
	"-ka",
	"--keepalive",
	required=False,
	action="store_true",
	help="Logs into the accounts to keep them alive.",
)
parser.add_argument(
	"-e",
	"--extract",
	required=False,
	action="store_true",
	help="Extracts the credentials to a file.",
)
parser.add_argument(
	"-v",
	"--verbose",
	required=False,
	action="store_true",
	help="Verbose logging (registration steps, mail addresses, keepalive storage).",
)
parser.add_argument(
	"-f", "--file", required=False, help="Uploads a file to the account."
)
parser.add_argument(
	"-p",
	"--public",
	required=False,
	action="store_true",
	help="Generates a public link to the uploaded file, use with -f",
)
parser.add_argument(
	"-l",
	"--loop",
	required=False,
	help="Loops the program for a specified amount of times.",
	type=int,
)

console_args = parser.parse_args()


def setup() -> Tuple[str, Config]:
	"""Sets up the configs so everything runs smoothly."""

	executable_path = ""
	config = read_config()

	if config is None:
		write_default_config()
		config = concrete_read_config()
	else:
		executable_path = config.executablePath

	# If no Chromium based browser is found, ask the user for the path to one.
	if not executable_path:
		p_print(
			"Failed to find a Chromium based browser. Please make sure you have one installed.",
			Colours.FAIL,
		)
		executable_path = input(
			"Please enter the path to a Chromium based browser's executable: "
		)
		if os.path.exists(executable_path):
			p_print("Found executable!", Colours.OKGREEN)
			write_config("executablePath", executable_path, config)
		else:
			p_print("Failed to find executable!", Colours.FAIL)
			sys.exit(1)

	return executable_path, config


def loop_registrations(loop_count: int, executable_path: str, config: Config):
	"""Registers accounts in a loop."""
	for _ in range(loop_count):
		p_print(f"Loop {_ + 1}/{loop_count}", Colours.OKGREEN)
		clear_tmp()

		asyncio.run(register(None, executable_path, config))


async def register(
	credentials: Credentials | None, executable_path: str, config: Config
):
	"""Registers and verifies mega.nz account.

	MEGA's confirmation email is sometimes delayed or not delivered by the
	mail provider. To stay robust we retry the whole registration (with a
	fresh email address) a few times before giving up.
	"""
	max_attempts = 4
	message = None

	# Silence benign pyppeteer teardown warnings emitted during browser close.
	asyncio.get_running_loop().set_exception_handler(_quiet_async_exceptions)

	p_print(f"Launching browser ({executable_path}) ...", Colours.HEADER)
	browser = await pyppeteer.launch(
		{
			"headless": True,
			"ignoreHTTPSErrors": True,
			"userDataDir": f"{os.getcwd()}/tmp",
			"args": args,
			"executablePath": executable_path,
			"autoClose": False,  # We run into runtime errors if we use autoClose
			"ignoreDefaultArgs": ["--enable-automation", "--disable-extensions"],
		}
	)

	context = await browser.createIncognitoBrowserContext()

	try:
		for attempt in range(1, max_attempts + 1):
			p_print(
				f"=== Registration attempt {attempt}/{max_attempts} ===",
				Colours.HEADER,
			)
			credentials = await generate_mail()
			page = await context.newPage()
			try:
				await type_name(page, credentials)
				await type_password(page, credentials)
				await finish_form(page, credentials)

				mail = await mail_login(credentials)
				await asyncio.sleep(1.5)
				try:
					message = await get_mail(mail)
				except CouldNotGetMessagesException:
					p_print(
						f"Confirmation email not received (attempt {attempt}/{max_attempts}). "
						"Retrying with a new email address...",
						Colours.WARNING,
					)
					await page.close()
					continue

				try:
					await initial_setup(context, message, credentials)
					break  # account confirmed successfully
				except RuntimeError as e:
					p_print(
						f"Account confirmation failed ({e}). "
						f"Retrying with a new email address (attempt {attempt}/{max_attempts})...",
						Colours.WARNING,
					)
					await page.close()
					continue
			except Exception as e:
				p_print(
					f"Registration step failed ({e}). "
					f"Retrying with a new email address (attempt {attempt}/{max_attempts})...",
					Colours.WARNING,
				)
				try:
					await page.close()
				except Exception:
					pass
				continue
	finally:
		# Always release the browser, even if we gave up or crashed mid-flow.
		try:
			await browser.close()
		except Exception:
			pass

	if message is None:
		p_print(
			"Gave up registering the account after several attempts.",
			Colours.FAIL,
		)
		sys.exit(1)

	p_print("Verified account.", Colours.OKGREEN)
	p_print(
		f"Email: {credentials.email}\nPassword: {credentials.password}",
		Colours.OKCYAN,
	)

	try:
		delete_default(credentials)
	except Exception as e:
		p_print(
			f"Warning: could not remove the default welcome file: {e}",
			Colours.WARNING,
		)
	p_print("Saving credentials ...", Colours.HEADER)
	save_credentials(credentials, config.accountFormat)

	if console_args.file is not None:
		try:
			file_size = os.path.getsize(console_args.file)
		except OSError:
			file_size = 0
		if os.path.exists(console_args.file) and 0 < file_size < 2e10:
			if file_size >= 5e9:
				p_print(
					"File is larger than 5GB, mega.nz limits traffic to 5GB per IP.",
					Colours.WARNING,
				)
			upload_file(console_args.public, console_args.file, credentials)
		else:
			p_print("File not found or invalid.", Colours.FAIL)
	if console_args.loop is None or console_args.loop <= 1:
		p_print("Done.", Colours.OKGREEN)
		sys.exit(0)


if __name__ == "__main__":
	clear_console()
	set_verbose(console_args.verbose)
	check_for_updates()

	executable_path, config = setup()
	if not executable_path:
		p_print("Failed while setting up!", Colours.FAIL)
		sys.exit(1)

	if console_args.extract:
		p_print("Extracting credentials to credentials.txt ...", Colours.HEADER)
		extract_credentials(config.accountFormat)
	elif console_args.keepalive:
		p_print("Keeping accounts alive (logging in) ...", Colours.HEADER)
		keepalive(console_args.verbose)
	elif console_args.loop is not None and console_args.loop > 1:
		loop_registrations(console_args.loop, executable_path, config)
	else:
		clear_tmp()
		asyncio.run(register(None, executable_path, config))
