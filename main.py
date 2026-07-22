"""Main file for the project, handles the arguments and calls the other files."""

import asyncio
import argparse
import os
import sys
import time
import subprocess
from typing import Tuple
import pyppeteer

# When available, import pyperclip for clipboard copy.
try:
	import pyperclip as _pyperclip

	_HAS_CLIPBOARD = True
except ImportError:
	_HAS_CLIPBOARD = False

# tenacity (a transitive dependency of mega.py) uses @asyncio.coroutine
# in its _asyncio module, which was removed in Python 3.11. If we're
# running on a Python where it's absent, restore it as a no-op shim so
# tenacity can still import cleanly. This works both for the frozen EXE
# (built with PyInstaller on Python 3.12) and for source installs on
# Python 3.11+.
if not hasattr(asyncio, "coroutine"):
	asyncio.coroutine = lambda f: f  # no-op decorator

from services.alive import keepalive
from services.upload import upload_file
from services.extract import extract_credentials
from services.download import _action_browse_cloud
from utilities.fs import (
	Config,
	concrete_read_config,
	read_config,
	merge_config,
	write_config,
	write_default_config,
	save_credentials,
	save_credentials_csv,
	save_credentials_jsonl,
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
from pymailtm.pymailtm import CouldNotGetAccountException, CouldNotGetMessagesException
from utilities.etc import (
	Credentials,
	p_print,
	Colours,
	clear_tmp,
	auto_update,
	delete_default,
	ProxyManager,
	LoopState,
	save_checkpoint,
	load_checkpoint,
	clear_checkpoint,
	separator,
	elapsed,
	VERSION,
	notify,
	capture_worker_output,
)
from utilities.menu import (
	Menu,
	MenuItem,
	_BACK,
	prompt_text,
	prompt_int,
	prompt_yes_no,
	prompt_path,
	pause,
)

# Proxy manager — populated from CLI args at startup.
_proxy_manager: ProxyManager = ProxyManager()

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


def _cleanup_pyppeteer(browser):
	"""Restore our SIGINT handler and kill the Chrome subprocess.

	pyppeteer replaces the SIGINT handler with its own ``_close_process``,
	which crashes with "Event loop is closed" when we later catch Ctrl+C
	in the TUI via ``input()``.  Call this after ``await browser.close()``.
	"""
	import signal as _signal

	# 1. Restore our SIGINT handler that pyppeteer overwrote.
	_signal.signal(_signal.SIGINT, _sigint_handler)

	# 2. Kill the actual Chrome subprocess so pyppeteer's atexit
	#    (which still runs) has nothing to do.
	try:
		proc = getattr(browser, "_process", None)
		if proc is not None:
			proc.kill()
	except Exception:
		pass


default_installs = [
	# Windows
	"C:/Program Files/Google/Chrome/Application/chrome.exe",
	"C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
	"C:/Program Files/BraveSoftware/Brave-Browser/Application/brave.exe",
	"C:/Program Files (x86)/BraveSoftware/Brave-Browser/Application/brave.exe",
	"C:/Program Files/Microsoft/Edge/Application/msedge.exe",
	os.path.expandvars("%LOCALAPPDATA%/Chromium/Application/chrome.exe"),
	os.path.expandvars("%LOCALAPPDATA%/Google/Chrome/Application/chrome.exe"),
	# Linux
	"/usr/bin/chromium",
	"/usr/bin/chromium-browser",
	"/usr/bin/google-chrome",
	"/usr/bin/google-chrome-stable",
	"/usr/bin/brave-browser",
	"/snap/bin/chromium",
	"/usr/bin/microsoft-edge",
	"/run/current-system/sw/bin/chromium",
	"/app/bin/chromium",
	# macOS
	"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
	"/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
	"/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
	"/opt/homebrew/bin/chromium",
]


def _build_browser_args(proxy_override: str | None = None) -> list[str]:
	"""Build browser launch args, optionally adding proxy."""
	base = [
		"--no-sandbox",
		"--disable-setuid-sandbox",
		"--disable-gpu",
		"--disable-dev-shm-usage",
		"--no-first-run",
		"--disable-background-networking",
		"--disable-sync",
		"--disable-background-timer-throttling",
		"--disable-infobars",
		"--window-position=0,0",
		"--ignore-certificate-errors",
		"--ignore-certificate-errors-spki-list",
		'--user-agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0"',
	]
	if proxy_override:
		base.append(f"--proxy-server={proxy_override}")
	else:
		proxy = _proxy_manager.get_proxy()
		if proxy:
			base.append(f"--proxy-server={proxy}")
	return base


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
	"--upload-dir",
	required=False,
	help="Upload all files in a directory (non-recursive).",
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
parser.add_argument(
	"--proxy",
	required=False,
	default="",
	help="Single proxy URL (e.g. http://user:pass@host:port).",
)
parser.add_argument(
	"--proxy-file",
	required=False,
	default="",
	help="File with one proxy URL per line (rotation).",
)
parser.add_argument(
	"--proxy-per-attempt",
	required=False,
	action="store_true",
	help="Rotate proxy on every registration attempt (not just per batch).",
)
parser.add_argument(
	"--export-jsonl",
	required=False,
	action="store_true",
	help="Also export every saved account to credentials/accounts.jsonl (JSON Lines).",
)
parser.add_argument(
	"--prune",
	required=False,
	action="store_true",
	help="When used with --keepalive, delete credential files for accounts that fail login.",
)
parser.add_argument(
	"--interval",
	required=False,
	type=float,
	default=0,
	help="When used with --keepalive, loop continuously every N hours.",
)
parser.add_argument(
	"--resume",
	required=False,
	action="store_true",
	help="Resume an interrupted loop batch from the last checkpoint.",
)
parser.add_argument(
	"-j",
	"--parallel",
	required=False,
	type=int,
	default=1,
	help="Number of parallel workers when using --loop. Default 1 (sequential). "
	"Each worker gets its own browser and optionally a dedicated proxy.",
)
parser.add_argument(
	"--list-cloud",
	required=False,
	action="store_true",
	help="List files in the cloud for the most recent account.",
)
parser.add_argument(
	"--download-cloud",
	required=False,
	metavar="FILE_ID",
	default="",
	help="Download a file from cloud by its node ID (use --list-cloud to get IDs).",
)
parser.add_argument(
	"--download-dest",
	required=False,
	metavar="DIR",
	default=".",
	help="Destination directory for --download-cloud (default: current dir).",
)
parser.add_argument(
	"--version",
	required=False,
	action="store_true",
	help="Show version and exit.",
)
parser.add_argument(
	"--provider",
	required=False,
	metavar="NAME",
	default=None,
	help='Email provider: "mailtm" (default) or "guerrillamail".',
)
parser.add_argument(
	"--health",
	required=False,
	action="store_true",
	help="Show health dashboard (quota, age, status) for all saved accounts.",
)
parser.add_argument(
	"--json",
	required=False,
	action="store_true",
	help="Output health dashboard as JSON (use with --health).",
)

console_args = parser.parse_args()

# Validate --provider value early.
if console_args.provider is not None:
	from utilities.provider import get_provider, get_provider_names

	if get_provider(console_args.provider) is None:
		p_print(
			f"Unknown provider: '{console_args.provider}'. "
			f"Valid options: {get_provider_names() or 'none'}",
			Colours.FAIL,
		)
		sys.exit(1)

# --json only makes sense with --health.
if console_args.json and not console_args.health:
	p_print("--json requires --health (e.g. --health --json).", Colours.WARNING)
	sys.exit(1)


def setup() -> Tuple[str, Config]:
	"""Sets up the configs so everything runs smoothly."""

	executable_path = ""
	config = read_config()

	if config is None:
		config = write_default_config()
		# write_default_config may return None if the file already had content
		# (in which case read_config had a transient failure). Fall back to
		# concrete_read_config which errors on truly absent files.
		if config is None:
			config = concrete_read_config()
	else:
		executable_path = config.executablePath

	# Auto-detect a Chromium-based browser from known paths.
	if not executable_path:
		for candidate in default_installs:
			if os.path.exists(candidate):
				executable_path = candidate
				p_print(f"Found browser: {executable_path}", Colours.OKGREEN)
				write_config("executablePath", executable_path, config)
				break

	# If still not found, ask the user for the path.
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
	resume: bool = False,
	provider_name: str | None = None,
):
	"""Registers accounts in a loop, printing a summary at the end.

	Launching Chromium takes ~8 s, so we launch *one* browser and share it
	across all loop iterations instead of re-launching per-account.

	When ``resume=True`` and a checkpoint file exists, the loop skips
	already-completed iterations.
	"""
	separator("Loop mode", Colours.HEADER)
	successes, failures = 0, 0
	start = time.monotonic()
	skip = 0

	if resume:
		cp = load_checkpoint()
		if cp is not None:
			skip = cp.completed + cp.failed
			successes = cp.completed
			failures = cp.failed
			p_print(
				f"Resuming from checkpoint: {cp.completed} done, {cp.failed} failed, "
				f"skipping {skip} of {loop_count}",
				Colours.WARNING,
			)

	async def _run_all():
		nonlocal successes, failures, skip
		p_print(f"Launching browser ({executable_path}) ...", Colours.HEADER)
		browser = await pyppeteer.launch(
			{
				"headless": not visible,
				"ignoreHTTPSErrors": True,
				"userDataDir": f"{os.getcwd()}/tmp",
				"args": _build_browser_args(),
				"executablePath": executable_path,
				"autoClose": False,
				"ignoreDefaultArgs": ["--enable-automation", "--disable-extensions"],
			}
		)
		try:
			for i in range(loop_count):
				if skip > 0:
					skip -= 1
					continue
				p_print(f"Loop {i + 1}/{loop_count}", Colours.OKGREEN)
				# clear_tmp deliberately skipped here: the browser's user-data-dir
				# is tmp/, and clearing it would wipe the shared browser profile.
				# It was already cleaned once before launching the browser.
				try:
					await register(
						None,
						executable_path,
						config,
						visible=visible,
						max_attempts=max_attempts,
						export_csv=export_csv,
						provider_name=provider_name,
						_browser=browser,
					)
					successes += 1
				except SystemExit as e:
					if e.code is None or e.code == 0:
						successes += 1
					else:
						failures += 1
				# Save checkpoint after every iteration.
				save_checkpoint(
					LoopState(
						total=loop_count,
						completed=successes,
						failed=failures,
						started_at=start,
					)
				)
		finally:
			try:
				await browser.close()
			except Exception:
				pass

	asyncio.run(_run_all())
	clear_checkpoint()

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
	notify(
		"MegaTemp: Loop complete",
		f"{successes} OK / {failures} FAIL in {total}",
	)
	sys.exit(0)


def parallel_registrations(
	loop_count: int,
	executable_path: str,
	config: Config,
	parallelism: int,
	visible: bool = False,
	max_attempts: int = 4,
	export_csv: bool = False,
	provider_name: str | None = None,
):
	"""Register accounts concurrently using N parallel workers.

	Each worker launches its own Chromium browser. When proxies are
	configured with --proxy-file, each worker draws from the shared
	rotation so they naturally use different IPs.
	"""
	separator(f"Parallel mode ({parallelism} workers)", Colours.HEADER)
	successes, failures = 0, 0
	start = time.monotonic()
	_lock = asyncio.Lock()

	async def _worker(worker_id: int, proxy: str | None = None):
		nonlocal successes, failures
		p_print(
			f"Worker {worker_id} starting{' with proxy' if proxy else ''}...",
			Colours.OKCYAN,
		)

		_browser_kwargs = {
			"headless": not visible,
			"ignoreHTTPSErrors": True,
			"userDataDir": f"{os.getcwd()}/tmp_{worker_id}",
			"args": _build_browser_args(proxy_override=proxy),
			"executablePath": executable_path,
			"autoClose": False,
			"ignoreDefaultArgs": ["--enable-automation", "--disable-extensions"],
		}
		browser = await pyppeteer.launch(_browser_kwargs)

		try:
			while True:
				# Atomically claim a slot so two workers never both
				# see "room for one more" and over-create.
				async with _lock:
					if successes + failures >= loop_count:
						return
					# Optimistic claim — we will increment successes
					# or failures after the work finishes.
					successes += 1

				# Buffer all p_print/separator output from register()
				# and flush it atomically so multiple workers never
				# interleave their output.
				with capture_worker_output() as buf:
					try:
						await register(
							None,
							executable_path,
							config,
							visible=visible,
							max_attempts=max_attempts,
							export_csv=export_csv,
							provider_name=provider_name,
							_browser=browser,
						)
						# already counted as success above
					except SystemExit as e:
						async with _lock:
							if not (e.code is None or e.code == 0):
								# Undo optimistic claim, count as failure
								successes -= 1
								failures += 1
					except Exception as exc:
						buf.append((f"Worker {worker_id} error: {exc}", Colours.FAIL))
						async with _lock:
							# Undo optimistic claim, count as failure
							successes -= 1
							failures += 1
						# The browser may be in a bad state (Chrome
						# crashed, context leaked, etc).  Replace it so
						# the next iteration doesn't fail instantly.
						try:
							await browser.close()
						except Exception:
							pass
						browser = await pyppeteer.launch(_browser_kwargs)

				# Flush the captured output under the lock so it
				# appears as one contiguous block per registration.
				async with _lock:
					for text, colour in buf:
						p_print(text, colour)
		finally:
			try:
				await browser.close()
			except Exception:
				pass

	async def _run_all():
		proxies = _proxy_manager.distribute(parallelism)
		tasks = [_worker(i, proxy=proxies[i]) for i in range(parallelism)]
		await asyncio.gather(*tasks)

	asyncio.run(_run_all())

	total = elapsed(start)
	separator("Parallel summary", Colours.HEADER)
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
	notify(
		"MegaTemp: Parallel complete",
		f"{successes} OK / {failures} FAIL in {total}",
	)
	sys.exit(0)


async def register(
	credentials: Credentials | None,
	executable_path: str,
	config: Config,
	visible: bool = False,
	max_attempts: int = 4,
	export_csv: bool = False,
	provider_name: str | None = None,
	_browser=None,  # internal: reuse across loop iterations
):
	"""Registers and verifies a mega.nz account.

	MEGA's confirmation email is sometimes delayed or not delivered by the
	mail provider. To stay robust we retry the whole registration (with a
	fresh email address) a few times before giving up.

	When called from loop mode, pass a shared ``_browser`` so Chromium is
	launched once instead of per-iteration.
	"""
	message = None
	start = time.monotonic()
	provider_name = (
		provider_name or getattr(config, "emailProvider", "mailtm") or "mailtm"
	)

	# Silence benign pyppeteer teardown warnings emitted during browser close.
	asyncio.get_running_loop().set_exception_handler(_quiet_async_exceptions)

	own_browser = _browser is None
	browser = _browser

	# Generate the first email address while the browser launches (parallelism).
	first_mail_task = (
		asyncio.create_task(generate_mail(provider_name)) if browser is None else None
	)

	if browser is None:
		p_print(f"Launching browser ({executable_path}) ...", Colours.HEADER)
		browser = await pyppeteer.launch(
			{
				"headless": not visible,
				"ignoreHTTPSErrors": True,
				"userDataDir": f"{os.getcwd()}/tmp",
				"args": _build_browser_args(),
				"executablePath": executable_path,
				"autoClose": False,  # We run into runtime errors if we use autoClose
				"ignoreDefaultArgs": ["--enable-automation", "--disable-extensions"],
			}
		)

	context = await browser.createIncognitoBrowserContext()

	try:
		for attempt in range(1, max_attempts + 1):
			separator(f"Registration attempt {attempt}/{max_attempts}")
			page = None
			try:
				if attempt == 1 and first_mail_task is not None:
					credentials = await first_mail_task
				else:
					credentials = await generate_mail(provider_name)
				page = await context.newPage()
				await type_name(page, credentials)
				await type_password(page, credentials)
				await finish_form(page, credentials)

				mail = await mail_login(credentials, provider_name)
				# No initial delay — start polling immediately;
				# get_mail handles backoff internally.
				try:
					message = await get_mail(mail)
				except (CouldNotGetMessagesException, LookupError):
					p_print(
						f"Confirmation email not received (attempt {attempt}/{max_attempts}). "
						"Retrying with a new email address...",
						Colours.WARNING,
					)
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
					continue
			except CouldNotGetAccountException:
				p_print(
					f"Could not generate email address (attempt {attempt}/{max_attempts}). "
					"Retrying...",
					Colours.WARNING,
				)
				continue
			except Exception as e:
				p_print(
					f"Registration step failed ({e}). "
					f"Retrying with a new email address (attempt {attempt}/{max_attempts})...",
					Colours.WARNING,
				)
				continue
			finally:
				if page is not None:
					try:
						await page.close()
					except Exception:
						pass
	finally:
		# Release the incognito context (always).
		try:
			await context.close()
		except Exception:
			pass
		# Only close the browser when we own it (single-account mode).
		if own_browser:
			try:
				await browser.close()
				# Suppress pyppeteer's atexit handler to avoid
				# "Event loop is closed" crash when the TUI calls input()
				# later (the atexit tries to killChrome() on a dead loop).
				_cleanup_pyppeteer(browser)
			except Exception:
				pass

	if message is None:
		p_print(
			"Gave up registering the account after several attempts.",
			Colours.FAIL,
		)
		sys.exit(1)

	# After the guard above, credentials is guaranteed to have been set by
	# a successful loop iteration. Assert for mypy's sake.
	assert credentials is not None

	p_print(
		f"Account verified in {elapsed(start)}.",
		Colours.OKGREEN,
	)
	p_print("Verified account.", Colours.OKGREEN)
	p_print(
		f"Email: {credentials.email}\nPassword: {credentials.password}",
		Colours.OKCYAN,
	)

	# Fire-and-forget delete_default in a background thread so the
	# MEGA API call (~3-5s) does not block the main flow.
	_delete_task = asyncio.create_task(asyncio.to_thread(delete_default, credentials))

	p_print("Saving credentials ...", Colours.HEADER)
	save_credentials(credentials, config.accountFormat)
	if export_csv:
		save_credentials_csv(credentials)
	if console_args.export_jsonl:
		save_credentials_jsonl(credentials)

	# Give delete_default up to 5s to finish in the background while we
	# save credentials and (optionally) upload a file. If it takes longer
	# we move on — it's best-effort cleanup.
	try:
		await asyncio.wait_for(_delete_task, timeout=5.0)
	except asyncio.TimeoutError:
		pass
	except Exception as e:
		p_print(
			f"Warning: could not remove the default welcome file: {e}",
			Colours.WARNING,
		)

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
	elif console_args.upload_dir is not None:
		if not os.path.isdir(console_args.upload_dir):
			p_print(f"Directory not found: {console_args.upload_dir}", Colours.FAIL)
		else:
			import glob as _glob

			files = sorted(
				f
				for f in _glob.glob(os.path.join(console_args.upload_dir, "*"))
				if os.path.isfile(f)
			)
			if not files:
				p_print(f"No files in {console_args.upload_dir}", Colours.WARNING)
			else:
				p_print(
					f"Uploading {len(files)} file(s) from {console_args.upload_dir}...",
					Colours.HEADER,
				)
				for f in files:
					upload_file(console_args.public, f, credentials)
	if console_args.loop is None or console_args.loop <= 1:
		p_print("Done.", Colours.OKGREEN)
		sys.exit(0)


# --------------------------------------------------------------------------- #
# Interactive TUI
# --------------------------------------------------------------------------- #
# Runtime settings that the menu can toggle. They feed directly into register().
# Initialised from saved config so changes persist across sessions.
_SETTINGS = {}


def _load_settings():
	global _SETTINGS
	cfg = read_config()
	_SETTINGS = {
		"attempts": cfg.maxAttempts if cfg else 4,
		"visible": cfg.visibleBrowser if cfg else False,
		"export_csv": cfg.csvExport if cfg else False,
		"export_jsonl": False,
	}


def _save_settings():
	merge_config(
		{
			"maxAttempts": _SETTINGS["attempts"],
			"visibleBrowser": _SETTINGS["visible"],
			"csvExport": _SETTINGS["export_csv"],
		}
	)


_load_settings()


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
	parallel = prompt_int("Parallel workers (1 = sequential)", 1, 1, 50)
	est_secs = count * 35 // max(parallel, 1)
	mins, secs = divmod(est_secs, 60)
	est_str = f"{int(mins)}m {secs}s" if mins else f"{secs}s"
	p_print(
		f"Creating {count} accounts ({parallel} worker(s)) — est. ~{est_str}",
		Colours.WARNING,
	)
	if not prompt_yes_no("Continue?"):
		return
	try:
		if parallel > 1:
			parallel_registrations(
				count,
				executable_path,
				config,
				parallelism=parallel,
				visible=_SETTINGS["visible"],
				max_attempts=_SETTINGS["attempts"],
				export_csv=_SETTINGS["export_csv"],
			)
		else:
			loop_registrations(
				count,
				executable_path,
				config,
				visible=_SETTINGS["visible"],
				max_attempts=_SETTINGS["attempts"],
				export_csv=_SETTINGS["export_csv"],
			)
	except SystemExit:
		pass
	pause("Press Enter to return to the menu...")


def _action_view_credentials(config):
	"""List saved credentials with file size and a masked password.

	Interactive key bindings:
	  p  — toggle password reveal
	  c  — copy email to clipboard (if pyperclip available)
	  C  — copy password to clipboard
	  d  — delete the selected credential (after confirmation)
	  j/k or up/down — navigate
	  q  — return to menu
	"""
	import json

	folder = "./credentials"
	if not os.path.isdir(folder):
		p_print("No credentials folder found.", Colours.WARNING)
		pause()
		return

	json_files = sorted([f for f in os.listdir(folder) if f.endswith(".json")])
	if not json_files:
		p_print("No saved credentials yet.", Colours.WARNING)
		pause()
		return

	_show_passwords = False
	_selected = 0
	_filter = ""

	while True:
		# Filter files by email, notes, or tags
		filtered = json_files
		if _filter:
			fl = _filter.lower()
			filtered = [f for f in json_files if fl in f.lower()]
		separator(
			f"Saved credentials ({len(filtered)}/{len(json_files)})"
			f" {'[passwords shown]' if _show_passwords else ''}"
			f" {'[filter: ' + _filter + ']' if _filter else ''}",
			Colours.HEADER,
		)
		if not filtered and _filter:
			p_print(
				f"  No accounts match '{_filter}'. Press [Esc] to clear filter.",
				Colours.WARNING,
			)
		for idx, f in enumerate(filtered):
			path = os.path.join(folder, f)
			try:
				with open(path, "r", encoding="utf-8") as fh:
					data = json.load(fh)
			except (json.JSONDecodeError, OSError):
				p_print(f"  ! {f} (unreadable)", Colours.WARNING)
				continue
			email = data.get("email", "?")
			if len(email) > 38:
				email = email[:35] + "..."
			pw = data.get("password", "")
			if _show_passwords:
				pw_display = pw if pw else "?"
			else:
				pw_display = ("*" * max(len(pw) - 2, 0)) + pw[-2:] if pw else "?"
			# Strength indicator when shown
			strength_info = ""
			if _show_passwords and pw:
				from utilities.password_strength import strength_label

				_label, _colour = strength_label(pw)
				strength_info = f" {_colour}{_label}\033[0m"
			size = os.path.getsize(path)
			tags_str = data.get("tags", "")
			notes_str = data.get("notes", "")
			tag_display = f" [{tags_str}]" if tags_str else ""
			note_display = f" {notes_str[:20]}" if notes_str else ""
			marker = ">" if idx == _selected else " "
			p_print(
				f" {marker} {email:<38} pw:{pw_display:<14} {size}B{tag_display}"
				f"{note_display}{strength_info}",
				Colours.OKGREEN if idx == _selected else Colours.OKCYAN,
			)
		p_print(
			"  [p] reveal  [c] copy email  [C] copy pw  [d] delete"
			"  [n] notes  [t] tag  [/] search  [Esc] clear  [q] back",
			Colours.WARNING,
		)
		key = input().strip().lower()
		if key == "q":
			break
		elif key == "p":
			_show_passwords = not _show_passwords
		elif key == "/":
			new_filter = prompt_text("Search (email/notes/tags)")
			if new_filter:
				_filter = new_filter
				_selected = 0
		elif key == "esc" or key == "\x1b" or key == chr(27):
			_filter = ""
			_selected = 0
		elif key == "n" and filtered:
			target = filtered[_selected]
			path = os.path.join(folder, target)
			try:
				with open(path, "r", encoding="utf-8") as fh:
					data = json.load(fh)
				cur_notes = data.get("notes", "")
				new_notes = prompt_text(f"Notes for {target}", default=cur_notes)
				if new_notes is not None:
					data["notes"] = new_notes
					with open(path, "w", encoding="utf-8") as fh:
						json.dump(data, fh, indent=2)
			except (OSError, json.JSONDecodeError) as e:
				p_print(f"Failed to update notes: {e}", Colours.FAIL)
		elif key == "t" and filtered:
			target = filtered[_selected]
			path = os.path.join(folder, target)
			try:
				with open(path, "r", encoding="utf-8") as fh:
					data = json.load(fh)
				cur_tags = data.get("tags", "")
				new_tags = prompt_text(
					f"Tags for {target} (comma-separated)", default=cur_tags
				)
				if new_tags is not None:
					data["tags"] = new_tags
					with open(path, "w", encoding="utf-8") as fh:
						json.dump(data, fh, indent=2)
			except (OSError, json.JSONDecodeError) as e:
				p_print(f"Failed to update tags: {e}", Colours.FAIL)
		elif key == "d" and filtered:
			target = filtered[_selected]
			if prompt_yes_no(f"Delete {target}? (cannot undo)"):
				try:
					os.remove(os.path.join(folder, target))
					p_print(f"Deleted {target}", Colours.OKGREEN)
					json_files.remove(target)
					filtered.remove(target)
					if _selected >= len(filtered):
						_selected = max(0, len(filtered) - 1)
				except OSError as e:
					p_print(f"Delete failed: {e}", Colours.FAIL)
		elif key == "a" and filtered:
			# Batch select all visible
			for f in filtered:
				path = os.path.join(folder, f)
				try:
					os.remove(path)
					p_print(f"Deleted {f}", Colours.OKGREEN)
				except OSError as e:
					p_print(f"Delete failed: {f}: {e}", Colours.FAIL)
			json_files = [f for f in json_files if f not in filtered]
			filtered = []
			_selected = 0
		elif key in ("c", "C") and filtered:
			if _HAS_CLIPBOARD:
				try:
					path = os.path.join(folder, filtered[_selected])
					with open(path, "r", encoding="utf-8") as fh:
						data = json.load(fh)
					_pyperclip.copy(data.get("email", ""))
					p_print("Email copied to clipboard!", Colours.OKGREEN)
				except Exception as e:
					p_print(f"Clipboard error: {e}", Colours.FAIL)
			else:
				p_print(
					"pyperclip not installed. Run: pip install pyperclip",
					Colours.WARNING,
				)
		elif key == "C" and filtered:
			if _HAS_CLIPBOARD:
				try:
					path = os.path.join(folder, filtered[_selected])
					with open(path, "r", encoding="utf-8") as fh:
						data = json.load(fh)
					_pyperclip.copy(data.get("password", ""))
					p_print("Password copied to clipboard!", Colours.OKGREEN)
				except Exception as e:
					p_print(f"Clipboard error: {e}", Colours.FAIL)
			else:
				p_print(
					"pyperclip not installed. Run: pip install pyperclip",
					Colours.WARNING,
				)
		elif key in ("j", "down") and filtered:
			_selected = (_selected + 1) % len(filtered)
		elif key in ("k", "up") and filtered:
			_selected = (_selected - 1) % len(filtered)
		if not filtered:
			p_print("No credentials remaining.", Colours.WARNING)
			break


def _action_export(config):
	"""Export saved credentials to a flat file."""
	if os.path.exists("credentials.txt") and not prompt_yes_no(
		"credentials.txt already exists. Overwrite?"
	):
		return
	p_print("Exporting credentials ...", Colours.HEADER)
	extract_credentials(config.accountFormat)
	pause("Press Enter to return to the menu...")


def _action_storage(config, json_output=False):
	"""Show health dashboard — quota, status, age, notes for all accounts."""
	from utilities.fs import list_credentials

	creds_list = list_credentials()
	if not creds_list:
		if json_output:
			import json as _json

			print(_json.dumps({"error": "No saved credentials."}))
		else:
			p_print("No saved credentials.", Colours.WARNING)
			pause()
		return

	from mega import Mega
	import datetime

	alive = 0
	dead = 0
	results = []
	if not json_output:
		p_print(
			"Health dashboard — querying storage for each account...", Colours.HEADER
		)

	for _fname, creds, _mtime in creds_list:
		age = datetime.datetime.now() - datetime.datetime.fromtimestamp(_mtime)
		days = age.days
		entry = {"email": creds.email, "age_days": days, "tags": creds.tags or ""}
		try:
			mega = Mega()
			mega.login(creds.email, creds.password)
			quota = mega.get_quota() / 1024  # get_quota() returns MB → convert to GB
			entry["status"] = "alive"
			entry["quota_gb"] = round(quota, 2)
			if json_output:
				results.append(entry)
			else:
				tag_str = f" [{creds.tags}]" if creds.tags else ""
				p_print(
					f"  {'✓':>3} {creds.email:<35} {quota:>5.1f} GB  {days:>3}d old"
					f"{tag_str}",
					Colours.OKGREEN,
				)
			alive += 1
		except Exception:
			entry["status"] = "dead"
			entry["quota_gb"] = 0
			if json_output:
				results.append(entry)
			else:
				tag_str = f" [{creds.tags}]" if creds.tags else ""
				p_print(
					f"  {'✗':>3} {creds.email:<35} {'DEAD':>8}  {days:>3}d old{tag_str}",
					Colours.FAIL,
				)
			dead += 1

	if json_output:
		import json as _json

		print(
			_json.dumps(
				{
					"accounts": results,
					"summary": {
						"alive": alive,
						"dead": dead,
						"total": len(creds_list),
					},
				},
				indent=2,
			)
		)
	else:
		separator(
			f"Summary: {alive} alive / {dead} dead / {len(creds_list)} total",
			Colours.HEADER,
		)
	pause("Press Enter to return to the menu...")


def _action_keepalive(config):
	"""Keep all saved accounts alive."""
	p_print("Keeping accounts alive (logging in) ...", Colours.HEADER)
	prune = prompt_yes_no("Remove dead accounts automatically?")
	keepalive(console_args.verbose, prune=prune)
	pause("Press Enter to return to the menu...")


def _action_download_browser(_unused_executable_path, _unused_config):
	"""Try to download Chromium for the current platform."""
	try:
		p_print("Attempting to download Chromium via pyppeteer...", Colours.HEADER)
		subprocess.check_call(
			[sys.executable, "-m", "pyppeteer", "install"],
			timeout=120,
		)
		p_print("Chromium downloaded successfully!", Colours.OKGREEN)
		# Try to find it and update config.
		import glob as _glob

		candidates = (
			_glob.glob(
				os.path.expanduser(
					"~/.local/share/pyppeteer/local-chromium/*/chrome-linux*/chrome"
				)
			)
			+ _glob.glob(
				os.path.expanduser(
					"~/.local/share/pyppeteer/local-chromium/*/chrome-win/chrome.exe"
				)
			)
			+ _glob.glob(
				os.path.expanduser(
					"~/.local/share/pyppeteer/local-chromium/*/chrome-mac*/Chromium.app/Contents/MacOS/Chromium"
				)
			)
		)
		if candidates:
			cfg = read_config()
			if cfg:
				write_config("executablePath", candidates[0], cfg)
				p_print(f"Auto-configured: {candidates[0]}", Colours.OKGREEN)
	except Exception as e:
		p_print(f"Failed to download Chromium: {e}", Colours.FAIL)
	pause("Press Enter to return to the menu...")


def _action_edit_config(_unused_executable_path, config):
	"""Edit config.json settings via interactive prompts."""
	from utilities.fs import read_config, write_config

	cfg = read_config()
	if cfg is None:
		p_print("Config not available.", Colours.FAIL)
		return

	p_print("Editing configuration. Leave blank to keep current value.", Colours.HEADER)
	path = prompt_text(
		"Browser executable path",
		default=cfg.executablePath or "(auto-detect)",
	)
	if path:
		write_config("executablePath", path, cfg)
	fmt = prompt_text(
		"Account format",
		default=cfg.accountFormat or "(JSON per account)",
	)
	if fmt is not None:
		merge_config({"accountFormat": fmt})
	proxy = prompt_text(
		"Proxy URL",
		default=cfg.proxy or "(none)",
	)
	if proxy is not None:
		merge_config({"proxy": proxy})
	p_print("Configuration updated.", Colours.OKGREEN)
	pause("Press Enter to return to the menu...")


def _pick_credentials(
	executable_path: str = "", config: Config | None = None
) -> Credentials | None:
	"""Show a numbered list of saved accounts and let the user pick one.

	When *config* is given, an extra option 0 is shown so the user can
	create a brand-new account on the spot and then upload to it.
	"""
	from utilities.fs import list_credentials

	creds_list = list_credentials()
	can_create = bool(executable_path and config)

	if not creds_list and not can_create:
		p_print("No saved credentials.", Colours.WARNING)
		return None

	separator("Select account", Colours.HEADER)
	if can_create:
		p_print("   0. Create a new account", Colours.OKGREEN)
	for idx, (_fname, creds, _) in enumerate(creds_list, start=1):
		p_print(f"  {idx:>3}. {creds.email}", Colours.OKCYAN)
	go_back_idx = len(creds_list) + 1
	p_print(f"  {go_back_idx:>3}. Go back", Colours.WARNING)

	minimum = 0 if can_create else 1
	default = 0 if can_create else 1
	choice = prompt_int("Account number", default, minimum, go_back_idx)

	if can_create and choice == 0:
		p_print("Creating a new account...", Colours.HEADER)
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
		# Re-read — register() saved the new account to disk.
		creds_list = list_credentials()
		if creds_list:
			creds_list.sort(key=lambda x: x[2], reverse=True)
			return creds_list[0][1]
		p_print("Account creation did not produce credentials.", Colours.FAIL)
		return None

	if choice == go_back_idx:
		return None

	return creds_list[choice - 1][1]


def _action_upload_dir(executable_path, config):
	"""Prompt for a directory, then upload all files inside (non-recursive)."""
	import glob

	raw = prompt_path("Path to directory to upload")
	path = os.path.expanduser(raw.strip().strip("'\""))
	if not os.path.isdir(path):
		p_print(f"Directory not found: {path}", Colours.FAIL)
		pause()
		return
	files = sorted(f for f in glob.glob(os.path.join(path, "*")) if os.path.isfile(f))
	if not files:
		p_print(f"No files found in {path}", Colours.WARNING)
		pause()
		return
	public = prompt_yes_no("Generate public share links?")
	p_print(f"Uploading {len(files)} file(s) from {path}...", Colours.HEADER)
	creds = _pick_credentials(executable_path, config)
	if creds is None:
		return
	for f in files:
		upload_file(public, f, creds)
	pause("Press Enter to return to the menu...")


def _action_upload(executable_path, config):
	"""Prompt for a file and (optional) public link, then upload."""

	def _clean_path(raw: str) -> str:
		"""Strip surrounding quotes and expand ``~``."""
		s = raw.strip()
		if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
			s = s[1:-1]
		return os.path.expanduser(s)

	while True:
		path = _clean_path(prompt_path("Path to file to upload"))
		if path and os.path.exists(path):
			break
		p_print("File not found.", Colours.FAIL)
		if not prompt_yes_no("Try a different path?"):
			return
	public = prompt_yes_no("Generate a public share link?")
	creds = _pick_credentials(executable_path, config)
	if creds is None:
		return
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
		MenuItem(
			"Auto JSONL Export",
			lambda: _toggle("export_jsonl"),
			"Also write each account to accounts.jsonl",
			value=lambda: "Yes" if _SETTINGS["export_jsonl"] else "No",
		),
		MenuItem(
			"Edit Config",
			lambda: _action_edit_config("", None),
			"executablePath, accountFormat, proxy",
		),
		MenuItem(
			"Download Chromium",
			lambda: _action_download_browser("", None),
			"Auto-download Chrome via pyppeteer",
		),
		MenuItem("Back", lambda: _BACK, "Return to the main menu"),
	]
	return Menu("Settings", items)


def _set_attempts():
	val = prompt_int("Max registration attempts", _SETTINGS["attempts"], 1, 50)
	_SETTINGS["attempts"] = val
	_save_settings()
	pause("Press Enter to return to the menu...")


def _toggle(key):
	_SETTINGS[key] = not _SETTINGS[key]
	_save_settings()
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
				"Storage Info",
				lambda: _action_storage(config),
				"Show free quota for every saved account",
			),
			MenuItem(
				"Upload File",
				lambda: _action_upload(executable_path, config),
				"Upload a file to the latest account",
			),
			MenuItem(
				"Upload Directory",
				lambda: _action_upload_dir(executable_path, config),
				"Upload all files in a folder",
			),
			MenuItem(
				"Browse Cloud",
				lambda: _action_browse_cloud(executable_path, config),
				"List and download files from your MEGA account",
			),
			MenuItem(
				"Settings",
				lambda: _open_settings(),
				"Attempts, visible mode, CSV export, config editor",
			),
			MenuItem(
				"Exit",
				lambda: (
					_BACK if prompt_yes_no("Are you sure you want to exit?") else None
				),
				"Quit MegaTemp",
			),
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


def _sigint_handler(signum, frame):
	"""Graceful Ctrl+C: don't dump a traceback, just exit cleanly."""
	p_print("\nInterrupted. Exiting...", Colours.WARNING)
	# Use os._exit() instead of sys.exit() to bypass asyncio cleanup
	# issues (e.g. "This event loop is already running") when pressed
	# inside parallel / loop mode.
	import os as _os

	_os._exit(0)


def _loop_keepalive(verbose: bool, prune: bool, interval_hours: float):
	"""Run keepalive in a loop every ``interval_hours``."""
	import time as _time

	interval_secs = interval_hours * 3600
	p_print(
		f"Keepalive loop: every {interval_hours:.1f}h (Ctrl+C to stop).",
		Colours.HEADER,
	)
	while True:
		keepalive(verbose, prune=prune)
		separator(f"Next run in {interval_hours:.1f}h", Colours.WARNING)
		_time.sleep(interval_secs)


def _setup_signal_handlers():
	import signal

	signal.signal(signal.SIGINT, _sigint_handler)


_setup_signal_handlers()

# Initialise global proxy manager from CLI args.
_proxy_manager = ProxyManager(
	proxy=console_args.proxy,
	proxy_file=console_args.proxy_file,
	per_attempt=console_args.proxy_per_attempt,
)

if __name__ == "__main__":
	set_verbose(console_args.verbose)
	auto_update()

	executable_path, config = setup()
	if not executable_path:
		p_print("Failed while setting up!", Colours.FAIL)
		sys.exit(1)

	if console_args.version:
		p_print(f"MegaTemp {VERSION}", Colours.OKGREEN)
		sys.exit(0)
	elif console_args.health:
		_action_storage(config, json_output=console_args.json)
		sys.exit(0)
	elif console_args.list_cloud:
		from services.download import _action_browse_cloud

		_action_browse_cloud(executable_path, config)
	elif console_args.download_cloud:
		from services.download import download_file, list_files
		from utilities.fs import list_credentials

		creds_list = list_credentials()
		if not creds_list:
			p_print("No saved credentials.", Colours.FAIL)
			sys.exit(1)
		# Use the most recent account.
		creds_list.sort(key=lambda x: x[2], reverse=True)
		creds = creds_list[0][1]
		dest = os.path.expanduser(console_args.download_dest)
		if not os.path.isdir(dest):
			p_print(f"Directory not found: {dest}", Colours.FAIL)
			sys.exit(1)
		# Look up the file by node ID from the file listing.
		file_id = console_args.download_cloud
		all_files = list_files(creds)
		match = next((f for f in all_files if str(f["id"]) == file_id), None)
		if match is None:
			p_print(
				f"File not found: {file_id}. Use --list-cloud to see available IDs.",
				Colours.FAIL,
			)
			sys.exit(1)
		download_file(creds, match["node"], dest)
	elif console_args.extract:
		p_print("Extracting credentials to credentials.txt ...", Colours.HEADER)
		extract_credentials(config.accountFormat)
	elif console_args.keepalive:
		p_print("Keeping accounts alive (logging in) ...", Colours.HEADER)
		if console_args.interval > 0:
			_loop_keepalive(
				console_args.verbose, console_args.prune, console_args.interval
			)
		else:
			keepalive(console_args.verbose, prune=console_args.prune)
	elif console_args.loop is not None and console_args.loop > 1:
		if console_args.parallel > 1:
			parallel_registrations(
				console_args.loop,
				executable_path,
				config,
				parallelism=console_args.parallel,
				visible=console_args.visible,
				max_attempts=console_args.attempts,
				export_csv=console_args.export_csv,
				provider_name=console_args.provider,
			)
		else:
			loop_registrations(
				console_args.loop,
				executable_path,
				config,
				console_args.visible,
				console_args.attempts,
				console_args.export_csv,
				resume=console_args.resume,
				provider_name=console_args.provider,
			)
	elif any(
		[
			console_args.file,
			console_args.upload_dir,
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
				provider_name=console_args.provider,
			)
		)
	else:
		# No flags -> launch the interactive TUI.
		_run_tui(executable_path, config)
