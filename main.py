"""Main file for the project, handles the arguments and calls the other files."""

import asyncio
import argparse
import os
import sys
import time
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
	save_credentials_csv,
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
	Colours,
	clear_tmp,
	check_for_updates,
	delete_default,
	separator,
	elapsed,
	VERSION,
)
from utilities.menu import (
	Menu,
	MenuItem,
	_BACK,
	prompt_text,
	prompt_int,
	prompt_yes_no,
	pause,
)

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
parser.add_argument(
	"-sh",
	"--visible",
	required=False,
	action="store_true",
	help="Run Chromium in visible (non-headless) mode so you can watch it work.",
)
parser.add_argument(
	"-a",
	"--attempts",
	required=False,
	type=int,
	default=4,
	help="Maximum registration attempts before giving up (default: 4).",
)
parser.add_argument(
	"-csv",
	"--export-csv",
	required=False,
	action="store_true",
	help="Also export every saved account to credentials/accounts.csv.",
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


def loop_registrations(
	loop_count: int,
	executable_path: str,
	config: Config,
	visible: bool = False,
	max_attempts: int = 4,
	export_csv: bool = False,
):
	"""Registers accounts in a loop, printing a summary at the end."""
	separator("Loop mode", Colours.HEADER)
	successes, failures = 0, 0
	start = time.monotonic()
	for i in range(loop_count):
		p_print(f"Loop {i + 1}/{loop_count}", Colours.OKGREEN)
		clear_tmp()
		try:
			asyncio.run(
				register(
					None,
					executable_path,
					config,
					visible=visible,
					max_attempts=max_attempts,
					export_csv=export_csv,
				)
			)
			successes += 1
		except SystemExit:
			# register() calls sys.exit(0) on success; a non-zero exit means
			# it gave up after exhausting its attempts.
			failures += 1

	total = elapsed(start)
	separator("Loop summary", Colours.HEADER)
	p_print(f"Total accounts: {loop_count}", Colours.OKBLUE)
	p_print(f"  Successful:   {successes}", Colours.OKGREEN)
	p_print(f"  Failed:       {failures}", Colours.WARNING)
	p_print(f"  Total time:   {total}", Colours.OKCYAN)
	if successes:
		per = (time.monotonic() - start) / successes
		mins, secs = divmod(per, 60)
		avg_per = f"{int(mins)}m {secs:.1f}s" if mins else f"{secs:.1f}s"
		p_print(f"  Avg / success: {avg_per}", Colours.OKCYAN)
	p_print("Done.", Colours.OKGREEN)
	sys.exit(0)


async def register(
	credentials: Credentials | None,
	executable_path: str,
	config: Config,
	visible: bool = False,
	max_attempts: int = 4,
	export_csv: bool = False,
):
	"""Registers and verifies a mega.nz account.

	MEGA's confirmation email is sometimes delayed or not delivered by the
	mail provider. To stay robust we retry the whole registration (with a
	fresh email address) a few times before giving up.
	"""
	message = None
	start = time.monotonic()

	# Silence benign pyppeteer teardown warnings emitted during browser close.
	asyncio.get_running_loop().set_exception_handler(_quiet_async_exceptions)

	p_print(f"Launching browser ({executable_path}) ...", Colours.HEADER)
	browser = await pyppeteer.launch(
		{
			"headless": not visible,
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
			separator(f"Registration attempt {attempt}/{max_attempts}")
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

	p_print(
		f"Account verified in {elapsed(start)}.",
		Colours.OKGREEN,
	)
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
	if export_csv:
		save_credentials_csv(credentials)

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


# --------------------------------------------------------------------------- #
# Interactive TUI
# --------------------------------------------------------------------------- #
# Runtime settings that the menu can toggle. They feed directly into register().
_SETTINGS = {
	"attempts": 4,
	"visible": False,
	"export_csv": False,
}


def _action_create_one(executable_path, config):
	"""Create a single account."""
	clear_tmp()
	try:
		asyncio.run(
			register(
				None,
				executable_path,
				config,
				visible=_SETTINGS["visible"],
				max_attempts=_SETTINGS["attempts"],
				export_csv=_SETTINGS["export_csv"],
			)
		)
	except SystemExit:
		pass
	pause("Press Enter to return to the menu...")


def _action_loop_create(executable_path, config):
	"""Prompt for a count, then loop-create."""
	clear_tmp()
	count = prompt_int("How many accounts to create", 5, 1, 1000)
	loop_registrations(
		count,
		executable_path,
		config,
		visible=_SETTINGS["visible"],
		max_attempts=_SETTINGS["attempts"],
		export_csv=_SETTINGS["export_csv"],
	)
	pause("Press Enter to return to the menu...")


def _action_view_credentials(config):
	"""List saved credentials with file size and a masked password."""
	import json

	folder = "./credentials"
	if not os.path.isdir(folder):
		p_print("No credentials folder found.", Colours.WARNING)
		pause()
		return

	json_files = [f for f in os.listdir(folder) if f.endswith(".json")]
	if not json_files:
		p_print("No saved credentials yet.", Colours.WARNING)
		pause()
		return

	separator(f"Saved credentials ({len(json_files)})", Colours.HEADER)
	for f in sorted(json_files):
		path = os.path.join(folder, f)
		try:
			with open(path, "r", encoding="utf-8") as fh:
				data = json.load(fh)
		except (json.JSONDecodeError, OSError):
			p_print(f"  ! {f} (unreadable)", Colours.WARNING)
			continue
		email = data.get("email", "?")
		pw = data.get("password", "")
		masked = ("*" * max(len(pw) - 2, 0)) + pw[-2:] if pw else "?"
		size = os.path.getsize(path)
		p_print(f"  {email:<38} pw:{masked:<14} {size}B", Colours.OKCYAN)
	pause()


def _action_export(config):
	"""Export saved credentials to a flat file."""
	p_print("Exporting credentials ...", Colours.HEADER)
	extract_credentials(config.accountFormat)
	pause("Press Enter to return to the menu...")


def _action_keepalive(config):
	"""Keep all saved accounts alive."""
	p_print("Keeping accounts alive (logging in) ...", Colours.HEADER)
	keepalive(console_args.verbose)
	pause("Press Enter to return to the menu...")


def _action_upload(executable_path, config):
	"""Prompt for a file and (optional) public link, then upload."""
	_ = executable_path
	path = prompt_text("Path to file to upload")
	if not path or not os.path.exists(path):
		p_print("File not found.", Colours.FAIL)
		pause()
		return
	public = prompt_yes_no("Generate a public share link?")
	# Upload needs an account; reuse the most recently created credential.
	import glob
	import json

	jsons = sorted(
		glob.glob("./credentials/*.json"), key=os.path.getmtime, reverse=True
	)
	if not jsons:
		p_print("No saved credentials to upload with.", Colours.FAIL)
		pause()
		return
	with open(jsons[0], "r", encoding="utf-8") as fh:
		data = json.load(fh)
	creds = Credentials(
		data.get("email", ""), data.get("emailPassword", ""), data.get("password", "")
	)
	upload_file(public, path, creds)
	pause("Press Enter to return to the menu...")


def _build_settings_menu():
	"""Submenu for toggling runtime settings."""
	items = [
		MenuItem(
			"Max Attempts",
			lambda: _set_attempts(),
			"Registration retries before giving up",
			value=lambda: str(_SETTINGS["attempts"]),
		),
		MenuItem(
			"Visible Browser",
			lambda: _toggle("visible"),
			"Show the Chromium window while working",
			value=lambda: "Yes" if _SETTINGS["visible"] else "No",
		),
		MenuItem(
			"Auto CSV Export",
			lambda: _toggle("export_csv"),
			"Also write each account to accounts.csv",
			value=lambda: "Yes" if _SETTINGS["export_csv"] else "No",
		),
		MenuItem("Back", lambda: _BACK, "Return to the main menu"),
	]
	return Menu("Settings", items)


def _set_attempts():
	val = prompt_int("Max registration attempts", _SETTINGS["attempts"], 1, 50)
	_SETTINGS["attempts"] = val
	pause("Press Enter to return to the menu...")


def _toggle(key):
	_SETTINGS[key] = not _SETTINGS[key]
	pause("Press Enter to return to the menu...")


def _run_tui(executable_path, config):
	"""Main interactive loop: shows the menu and dispatches selections."""
	while True:
		items = [
			MenuItem(
				"Create Account",
				lambda: _action_create_one(executable_path, config),
				"Register a single mega.nz account",
			),
			MenuItem(
				"Loop Create",
				lambda: _action_loop_create(executable_path, config),
				"Create many accounts in a row",
			),
			MenuItem(
				"View Credentials",
				lambda: _action_view_credentials(config),
				"List every saved account",
			),
			MenuItem(
				"Export Credentials",
				lambda: _action_export(config),
				"Write accounts to credentials.txt",
			),
			MenuItem(
				"Keep Alive Accounts",
				lambda: _action_keepalive(config),
				"Log in to every account to keep it active",
			),
			MenuItem(
				"Upload File",
				lambda: _action_upload(executable_path, config),
				"Upload a file to the latest account",
			),
			MenuItem(
				"Settings",
				lambda: _open_settings(),
				"Attempts, visible mode, CSV export",
			),
			MenuItem("Exit", lambda: _BACK, "Quit MegaTemp"),
		]
		menu = Menu(f"MegaTemp {VERSION}", items)
		result = menu.run()
		if result is _BACK:
			break


def _open_settings():
	"""Open the settings submenu; returns to main menu afterwards."""
	while True:
		sub = _build_settings_menu()
		result = sub.run()
		if result is _BACK:
			break


if __name__ == "__main__":
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
		loop_registrations(
			console_args.loop,
			executable_path,
			config,
			console_args.visible,
			console_args.attempts,
			console_args.export_csv,
		)
	elif any(
		[
			console_args.file,
			console_args.visible,
			console_args.attempts != 4,
			console_args.export_csv,
			console_args.verbose,
		]
	):
		# Headless / scripted invocation with explicit flags.
		clear_tmp()
		asyncio.run(
			register(
				None,
				executable_path,
				config,
				visible=console_args.visible,
				max_attempts=console_args.attempts,
				export_csv=console_args.export_csv,
			)
		)
	else:
		# No flags -> launch the interactive TUI.
		_run_tui(executable_path, config)
