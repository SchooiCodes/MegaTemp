"""Main file for the project, handles the arguments and calls the other files."""

import asyncio
import argparse
import os
import random
import sys
import time
import subprocess
from typing import Tuple
import pyppeteer
import pyppeteer.errors

# When available, import pyperclip for clipboard copy.
try:
	import pyperclip as _pyperclip

	_HAS_CLIPBOARD = True
except ImportError:
	_HAS_CLIPBOARD = False

# tenacity (a transitive dependency of mega.py) uses @asyncio.coroutine
# in its _asyncio module, which was removed in Python 3.11. If we're
import utilities.compat  # noqa: F401 — restores asyncio.coroutine for tenacity

from utilities.mega_patch import patch_mega

patch_mega()  # noqa: E402 — must run before service imports

from services.alive import keepalive  # noqa: E402
from services.upload import upload_file, get_mega_session, _upload_with_session  # noqa: E402
from services.extract import extract_credentials  # noqa: E402
from services.download import _action_browse_cloud  # noqa: E402
from utilities.fs import (  # noqa: E402
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
from utilities.web import (  # noqa: E402
	finish_form,
	generate_mail,
	type_name,
	type_password,
	initial_setup,
	mail_login,
	get_mail,
	set_verbose,
)
from pymailtm.pymailtm import CouldNotGetAccountException, CouldNotGetMessagesException  # noqa: E402
from utilities.etc import (  # noqa: E402
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
	set_quiet,
	send_webhook,
	capture_worker_output,
)
from utilities.menu import (  # noqa: E402
	Menu,
	MenuItem,
	_BACK,
	prompt_text,
	prompt_int,
	prompt_yes_no,
	prompt_path,
	pause,
)

# Cached working directory (syscall cache — avoid repeated os.getcwd() calls).
_CWD = os.getcwd()

# Cached browser base args (built once, reused across all launch calls).
_BROWSER_BASE_ARGS = [
	"--no-sandbox",
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

# Proxy manager — instantiated after CLI parsing so --proxy / --proxy-file
# are honoured. The real initialisation is at the bottom of the module.
_proxy_manager: ProxyManager | None = None

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


def _install_async_handler():
	try:
		asyncio.get_running_loop().set_exception_handler(_quiet_async_exceptions)
	except RuntimeError:
		pass


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
			proc.terminate()
			try:
				proc.wait(timeout=5)
			except Exception:
				proc.kill()
				proc.wait(timeout=2)
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
	base = list(_BROWSER_BASE_ARGS)
	if proxy_override:
		base.append(f"--proxy-server={proxy_override}")
	else:
		proxy = _proxy_manager.get_proxy()
		if proxy:
			base.append(f"--proxy-server={proxy}")
	return base


async def _launch_browser(kwargs: dict):
	"""Launch pyppeteer and close default about:blank pages."""
	last_error = None
	for attempt in range(2):
		try:
			browser = await pyppeteer.launch(kwargs)
			for pg in await browser.pages():
				await pg.close()
			import signal as _signal
			_signal.signal(_signal.SIGINT, _sigint_handler)
			return browser
		except Exception as exc:
			last_error = exc
			p_print(
				f"[browser] launch failed ({exc!r}), retrying...",
				Colours.WARNING,
			)
			if attempt == 0:
				clear_tmp()
				await asyncio.sleep(1)
	raise RuntimeError(
		f"Browser failed to launch after retry: {last_error!r}"
	) from last_error


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
	"--proxy-url",
	required=False,
	default="",
	help="URL to auto-fetch proxy list from (plain text or JSON array).",
)
parser.add_argument(
	"--export-jsonl",
	required=False,
	action="store_true",
	help="Also export every saved account to credentials/accounts.jsonl (JSON Lines).",
)
parser.add_argument(
	"--export-bitwarden",
	required=False,
	action="store_true",
	help="Export credentials in Bitwarden CSV format.",
)
parser.add_argument(
	"--export-onepassword",
	required=False,
	action="store_true",
	help="Export credentials in 1Password CSV format.",
)
parser.add_argument(
	"--export-keepass",
	required=False,
	action="store_true",
	help="Export credentials in KeePass CSV format.",
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
parser.add_argument(
	"--quiet",
	required=False,
	action="store_true",
	help="Suppress non-essential output for scripting.",
)
parser.add_argument(
	"--profile",
	required=False,
	default="",
	help="Config profile name (uses config-{name}.json instead of config.json).",
)
parser.add_argument(
	"--mail-timeout",
	required=False,
	type=int,
	default=120,
	help="Seconds to wait for MEGA confirmation email (default: 120).",
)
parser.add_argument(
	"--webhook-url",
	required=False,
	default="",
	help="URL to POST JSON payload on registration success/failure.",
)
parser.add_argument(
	"--encryption-password",
	required=False,
	default="",
	help="Optional password to encrypt stored credentials at rest.",
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

	from utilities.fs import set_config_profile
	if console_args.profile:
		set_config_profile(console_args.profile)

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


def _get_encryption_password(config) -> str:
	"""Resolve encryption password: CLI arg > config."""
	if console_args.encryption_password:
		return console_args.encryption_password
	return getattr(config, "encryptionPassword", "")


def loop_registrations(
	loop_count: int,
	executable_path: str,
	config: Config,
	visible: bool = False,
	max_attempts: int = 4,
	export_csv: bool = False,
	export_jsonl: bool = False,
	resume: bool = False,
	provider_name: str | None = None,
	webhook_url: str = "",
	encryption_password: str = "",
) -> None:
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
		browser = await _launch_browser(
			{
				"headless": not visible,
				"ignoreHTTPSErrors": True,
				"userDataDir": f"{_CWD}/tmp",
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
						export_jsonl=export_jsonl,
						provider_name=provider_name,
						webhook_url=webhook_url,
						encryption_password=encryption_password,
						_browser=browser,
					)
					successes += 1
				except SystemExit as e:
					if e.code is None or e.code == 0:
						successes += 1
					else:
						failures += 1
				# Save checkpoint every 5th iteration or every 30s.
				if successes + failures == 1 or (successes + failures) % 5 == 0 or (time.monotonic() - start) > 30:
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
			_cleanup_pyppeteer(browser)

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
	parallelism: int = 1,
	visible: bool = False,
	max_attempts: int = 4,
	export_csv: bool = False,
	export_jsonl: bool = False,
	provider_name: str | None = None,
	webhook_url: str = "",
	encryption_password: str = "",
) -> None:
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

		# Stagger worker launches with jitter so 10 workers don't all
		# hit MEGA from the same IP simultaneously and trigger rate limits.
		stagger = worker_id * 2.5 + random.uniform(0, 1.5)
		await asyncio.sleep(stagger)

		p_print(
			f"Worker {worker_id} starting{' with proxy' if proxy else ''}...",
			Colours.OKCYAN,
		)

		_browser_kwargs = {
			"headless": not visible,
			"ignoreHTTPSErrors": True,
			"userDataDir": f"{_CWD}/tmp_{worker_id}",
			"args": _build_browser_args(proxy_override=proxy),
			"executablePath": executable_path,
			"autoClose": False,
			"ignoreDefaultArgs": ["--enable-automation", "--disable-extensions"],
		}
		browser = await _launch_browser(_browser_kwargs)

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
							export_jsonl=export_jsonl,
							provider_name=provider_name,
							webhook_url=webhook_url,
							encryption_password=encryption_password,
							_browser=browser,
						)
						# already counted as success above
					except SystemExit as e:
						async with _lock:
							if not (e.code is None or e.code == 0):
								# Undo optimistic claim, count as failure
								successes -= 1
								failures += 1
						# Brief cooldown before trying the next account so we
						# don't hammer MEGA with back-to-back rate-limited requests.
						if failures > 0:
							await asyncio.sleep(1.0)
					except Exception as exc:
						buf.append((f"Worker {worker_id} error: {exc}", Colours.FAIL))
						async with _lock:
							successes -= 1
							failures += 1
						if isinstance(exc, (pyppeteer.errors.BrowserError, pyppeteer.errors.PageError, pyppeteer.errors.NetworkError)):
							try:
								await browser.close()
							except Exception:
								pass
							browser = await _launch_browser(_browser_kwargs)
						else:
							await asyncio.sleep(1.0)

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
			_cleanup_pyppeteer(browser)

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


_PROVIDER_FALLBACKS = {"mailtm": "guerrillamail", "guerrillamail": "mailtm"}


async def register(
	credentials: Credentials | None,
	executable_path: str,
	config: Config,
	visible: bool = False,
	max_attempts: int = 4,
	export_csv: bool = False,
	export_jsonl: bool = False,
	provider_name: str | None = None,
	webhook_url: str = "",
	encryption_password: str = "",
	_browser: object | None = None,  # internal: reuse across loop iterations
) -> Credentials | None:
	"""Registers and verifies a mega.nz account.

	MEGA's confirmation email is sometimes delayed or not delivered by the
	mail provider. To stay robust we retry the whole registration (with a
	fresh email address) a few times before giving up. If all attempts with
	the primary provider fail, we fall back to the alternative provider.

	When called from loop mode, pass a shared ``_browser`` so Chromium is
	launched once instead of per-iteration.
	"""
	_install_async_handler()
	message = None
	start = time.monotonic()
	primary_provider = (
		provider_name or getattr(config, "emailProvider", "mailtm") or "mailtm"
	)
	fallback_provider = _PROVIDER_FALLBACKS.get(primary_provider)

	own_browser = _browser is None
	browser = _browser

	for provider_attempt, prov in enumerate([primary_provider, fallback_provider]):
		if prov is None:
			break
		if provider_attempt > 0:
			p_print(
				f"Switching to fallback provider '{prov}'...",
				Colours.WARNING,
			)

		message = None
		first_mail_task = (
			asyncio.create_task(generate_mail(prov)) if browser is None else None
		)

		if browser is None and provider_attempt == 0:
			clear_tmp()
			p_print(f"Launching browser ({executable_path}) ...", Colours.HEADER)
			browser = await _launch_browser(
				{
					"headless": not visible,
					"ignoreHTTPSErrors": True,
					"userDataDir": f"{_CWD}/tmp",
					"args": _build_browser_args(),
					"executablePath": executable_path,
					"autoClose": False,
					"ignoreDefaultArgs": ["--enable-automation", "--disable-extensions"],
				}
			)

		context = await browser.createIncognitoBrowserContext()

		try:
			for attempt in range(1, max_attempts + 1):
				separator(f"Registration attempt {attempt}/{max_attempts} ({prov})")
				page = None
				try:
					if attempt == 1 and first_mail_task is not None:
						credentials = await first_mail_task
					else:
						credentials = await generate_mail(prov)
					page = await context.newPage()
					await type_name(page, credentials)
					await type_password(page, credentials)
					await finish_form(page, credentials)

					mail = await mail_login(credentials, prov)
					try:
						message = await get_mail(mail, max_attempts=config.mailTimeout)
					except (CouldNotGetMessagesException, LookupError):
						p_print(
							f"Confirmation email not received (attempt {attempt}/{max_attempts}). "
							"Retrying with a new email address...",
							Colours.WARNING,
						)
						await asyncio.sleep(min(1.0 * 1.5 ** (attempt - 1), 3.0))
						continue

					try:
						await initial_setup(context, message, credentials)
						break
					except RuntimeError as e:
						p_print(
							f"Account confirmation failed ({e}). "
							f"Retrying with a new email address (attempt {attempt}/{max_attempts})...",
							Colours.WARNING,
						)
						await asyncio.sleep(min(1.0 * 1.5 ** (attempt - 1), 3.0))
						continue
				except CouldNotGetAccountException:
					p_print(
						f"Could not generate email address (attempt {attempt}/{max_attempts}). "
						"Retrying...",
						Colours.WARNING,
					)
					await asyncio.sleep(min(1.0 * 1.5 ** (attempt - 1), 3.0))
					continue
				except Exception as e:
					p_print(
						f"Registration step failed ({e}). "
						f"Retrying with a new email address (attempt {attempt}/{max_attempts})...",
						Colours.WARNING,
					)
					await asyncio.sleep(min(1.0 * 1.5 ** (attempt - 1), 3.0))
					continue
				finally:
					if page is not None:
						try:
							await page.close()
						except Exception:
							pass

			if message is not None:
				break
		finally:
			try:
				await context.close()
			except Exception:
				pass

	if own_browser:
		try:
			await browser.close()
		except Exception:
			pass
		_cleanup_pyppeteer(browser)

	if message is None:
		p_print(
			"Gave up registering the account after several attempts.",
			Colours.FAIL,
		)
		await asyncio.to_thread(
			send_webhook,
			webhook_url,
			"registration_failed",
			{
				"provider": provider_name or config.emailProvider,
				"attempts": max_attempts,
				"timestamp": time.time(),
			},
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

	await asyncio.to_thread(
		send_webhook,
		webhook_url,
		"registration_success",
		{
			"email": credentials.email,
			"provider": provider_name or config.emailProvider,
			"timestamp": time.time(),
		},
	)

	# Fire-and-forget delete_default in a background thread so the
	# MEGA API call (~3-5s) does not block the main flow.
	asyncio.create_task(asyncio.to_thread(delete_default, credentials))

	credentials.lastLogin = time.time()

	p_print("Saving credentials ...", Colours.HEADER)
	await asyncio.gather(
		asyncio.to_thread(save_credentials, credentials, config.accountFormat, encryption_password),
		asyncio.to_thread(save_credentials_csv, credentials) if export_csv else asyncio.sleep(0),
		asyncio.to_thread(save_credentials_jsonl, credentials) if export_jsonl else asyncio.sleep(0),
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
		"export_jsonl": cfg.jsonlExport if cfg else False,
		"ka_interval": 0.0,
	}


def _save_settings():
	merge_config(
		{
			"maxAttempts": _SETTINGS["attempts"],
			"visibleBrowser": _SETTINGS["visible"],
			"csvExport": _SETTINGS["export_csv"],
			"jsonlExport": _SETTINGS["export_jsonl"],
		}
	)


_load_settings()


def _get_webhook_url(config) -> str:
	"""Resolve webhook URL: CLI arg > config."""
	if console_args.webhook_url:
		return console_args.webhook_url
	return getattr(config, "webhookUrl", "")


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
				export_jsonl=_SETTINGS["export_jsonl"],
				webhook_url=_get_webhook_url(config),
				encryption_password=_get_encryption_password(config),
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
					export_jsonl=_SETTINGS["export_jsonl"],
					webhook_url=_get_webhook_url(config),
					encryption_password=_get_encryption_password(config),
				)
			else:
				loop_registrations(
					count,
					executable_path,
					config,
					visible=_SETTINGS["visible"],
					max_attempts=_SETTINGS["attempts"],
					export_csv=_SETTINGS["export_csv"],
					export_jsonl=_SETTINGS["export_jsonl"],
					webhook_url=_get_webhook_url(config),
					encryption_password=_get_encryption_password(config),
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

	from utilities.fs import CREDENTIALS_DIR
	folder = CREDENTIALS_DIR
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
	_regex_mode = False

	def _preload():
		data = {}
		for f in json_files:
			path = os.path.join(folder, f)
			try:
				with open(path, "r", encoding="utf-8") as fh:
					data[f] = (json.load(fh), path)
			except (json.JSONDecodeError, OSError):
				data[f] = (None, path)
		return data

	_file_data = _preload()

	while True:
		# Filter files by email, notes, or tags
		filtered = json_files
		if _filter:
			if _regex_mode:
				import re as _re
				try:
					pat = _re.compile(_filter, _re.IGNORECASE)
					filtered = [f for f in json_files if pat.search(f)]
				except _re.error:
					filtered = []
			else:
				fl = _filter.lower()
				filtered = [f for f in json_files if fl in f.lower()]
		separator(
			f"Saved credentials ({len(filtered)}/{len(json_files)})"
			f" {'[passwords shown]' if _show_passwords else ''}"
			f" {'[regex]' if _regex_mode else ''}"
			f" {'[filter: ' + _filter + ']' if _filter else ''}",
			Colours.HEADER,
		)
		if not filtered and _filter:
			p_print(
				f"  No accounts match '{_filter}'. Press [Esc] to clear filter.",
				Colours.WARNING,
			)
		for idx, f in enumerate(filtered):
			data, path = _file_data.get(f, (None, os.path.join(folder, f)))
			if data is None:
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
			"  [p] reveal  [c] copy email  [C] copy pw  [d] delete  [n] notes"
			"  [t] tag  [/] search  [r] regex  [Esc] clear  [q] back",
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
			data, path = _file_data.get(target, (None, os.path.join(folder, target)))
			if data is not None:
				cur_notes = data.get("notes", "")
				new_notes = prompt_text(f"Notes for {target}", default=cur_notes)
				if new_notes is not None:
					data["notes"] = new_notes
					try:
						with open(path, "w", encoding="utf-8") as fh:
							json.dump(data, fh, indent=2)
						_file_data[target] = (data, path)
					except (OSError, json.JSONDecodeError) as e:
						p_print(f"Failed to update notes: {e}", Colours.FAIL)
			else:
				p_print(f"  ! {target} (unreadable)", Colours.WARNING)
		elif key == "t" and filtered:
			target = filtered[_selected]
			data, path = _file_data.get(target, (None, os.path.join(folder, target)))
			if data is not None:
				cur_tags = data.get("tags", "")
				new_tags = prompt_text(
					f"Tags for {target} (comma-separated)", default=cur_tags
				)
				if new_tags is not None:
					data["tags"] = new_tags
					try:
						with open(path, "w", encoding="utf-8") as fh:
							json.dump(data, fh, indent=2)
						_file_data[target] = (data, path)
					except (OSError, json.JSONDecodeError) as e:
						p_print(f"Failed to update tags: {e}", Colours.FAIL)
			else:
				p_print(f"  ! {target} (unreadable)", Colours.WARNING)
		elif key == "d" and filtered:
			target = filtered[_selected]
			if prompt_yes_no(f"Delete {target}? (cannot undo)"):
				try:
					os.remove(os.path.join(folder, target))
					p_print(f"Deleted {target}", Colours.OKGREEN)
					_file_data.pop(target, None)
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
		elif key == "r":
			_regex_mode = not _regex_mode
			p_print(
				f"Regex search: {'ON' if _regex_mode else 'OFF'}",
				Colours.OKGREEN if _regex_mode else Colours.WARNING,
			)
		elif key in ("c", "C") and filtered:
			if _HAS_CLIPBOARD:
				try:
					data, _ = _file_data.get(filtered[_selected], (None, None))
					if data is not None:
						_pyperclip.copy(data.get("email" if key == "c" else "password", ""))
						p_print(f"{'Email' if key == 'c' else 'Password'} copied to clipboard!", Colours.OKGREEN)
					else:
						p_print("Credential unreadable.", Colours.WARNING)
				except Exception as e:
					p_print(f"Clipboard error: {e}", Colours.FAIL)
		elif key in ("j", "down") and filtered:
			_selected = (_selected + 1) % len(filtered)
		elif key in ("k", "up") and filtered:
			_selected = (_selected - 1) % len(filtered)
		if not filtered:
			p_print("No credentials remaining.", Colours.WARNING)
			break


def _action_export(config):
	"""Export saved credentials to a flat file."""
	from utilities.fs import CREDENTIALS_TXT
	if os.path.exists(CREDENTIALS_TXT) and not prompt_yes_no(
		"credentials.txt already exists. Overwrite?"
	):
		return
	p_print("Exporting credentials ...", Colours.HEADER)
	extract_credentials(config.accountFormat)
	pause("Press Enter to return to the menu...")


def _storage_bar(quota_gb: float, width: int = 20) -> str:
	"""Render a simple ASCII bar showing storage usage vs 20 GB free tier."""
	full = 20.0  # MEGA free tier is 20 GB
	fraction = min(quota_gb / full, 1.0)
	filled = int(fraction * width)
	empty = width - filled
	bar = "\033[92m" + "█" * filled + "\033[90m" + "░" * empty + "\033[0m"
	return bar


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

	from concurrent.futures import ThreadPoolExecutor as _TPE

	alive = 0
	dead = 0
	results = []
	if not json_output:
		p_print(
			"Health dashboard — querying storage for each account...", Colours.HEADER
		)

	def _check_one(_fname, creds, _mtime):
		age = datetime.datetime.now() - datetime.datetime.fromtimestamp(_mtime)
		days = age.days
		entry = {"email": creds.email, "age_days": days, "tags": creds.tags or ""}
		if creds.lastLogin:
			last_login_dt = datetime.datetime.fromtimestamp(creds.lastLogin)
			login_age = (datetime.datetime.now() - last_login_dt).days
			login_str = f"{login_age}d ago" if login_age < 365 else ">1y ago"
		else:
			login_str = "never"
		try:
			mega = Mega()
			mega.login(creds.email, creds.password)
			quota = mega.get_quota() / 1024
			entry["status"] = "alive"
			entry["quota_gb"] = round(quota, 2)
			if not json_output:
				_tag_str = f" [{creds.tags}]" if creds.tags else ""
				p_print(
					f"  {'✓':>3} {creds.email:<35} {quota:>5.1f} GB {_storage_bar(quota, 20)} {days:>3}d old"
					f" ll:{login_str}{_tag_str}",
					Colours.OKGREEN,
				)
			return entry, "alive"
		except Exception:
			entry["status"] = "dead"
			entry["quota_gb"] = 0
			if not json_output:
				_tag_str = f" [{creds.tags}]" if creds.tags else ""
				p_print(
					f"  {'✗':>3} {creds.email:<35} {'DEAD':>8}  {days:>3}d old"
					f" ll:{login_str}{_tag_str}",
					Colours.FAIL,
				)
			return entry, "dead"

	with _TPE(max_workers=min(20, max(5, len(creds_list)))) as pool:
		futures = [
			pool.submit(_check_one, _fname, creds, _mtime)
			for _fname, creds, _mtime in creds_list
		]
		entries = [f.result() for f in futures]

	for entry, status in entries:
		if json_output:
			results.append(entry)
		if status == "alive":
			alive += 1
		else:
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
	if not json_output:
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
					export_jsonl=_SETTINGS["export_jsonl"],
					webhook_url=_get_webhook_url(config),
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
	try:
		mega = get_mega_session(creds)
	except Exception as e:
		p_print(f"Login failed for {creds.email}: {e}", Colours.FAIL)
		pause("Press Enter to return to the menu...")
		return
	for f in files:
		_upload_with_session(public, f, mega)
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
			"Generate Password",
			_action_generate_password,
			"Create a random strong password",
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


def _action_generate_password():
	"""Generate a random strong password and optionally copy to clipboard."""
	from utilities.password_strength import generate_password, strength_label
	length = prompt_int("Password length", default=20, minimum=8, maximum=128)
	pw = generate_password(length)
	_label, _colour = strength_label(pw)
	p_print(f"Generated password ({_label}): {pw}", Colours.OKGREEN)
	if prompt_yes_no("Copy to clipboard?"):
		try:
			import pyperclip as _pc
			_pc.copy(pw)
			p_print("Copied!", Colours.OKGREEN)
		except (ImportError, Exception) as e:
			p_print(f"Clipboard unavailable: {e}", Colours.WARNING)
	pause("Press Enter to return to the menu...")


def _action_export_bitwarden():
	"""Export credentials in Bitwarden CSV format."""
	from services.extract import export_bitwarden_csv
	p_print("Exporting to Bitwarden CSV...", Colours.HEADER)
	try:
		export_bitwarden_csv()
	except Exception as e:
		p_print(f"Export failed: {e}", Colours.FAIL)
	pause("Press Enter to return to the menu...")


def _action_export_onepassword():
	"""Export credentials in 1Password CSV format."""
	from services.extract import export_onepassword_csv
	p_print("Exporting to 1Password CSV...", Colours.HEADER)
	try:
		export_onepassword_csv()
	except Exception as e:
		p_print(f"Export failed: {e}", Colours.FAIL)
	pause("Press Enter to return to the menu...")


def _action_export_keepass():
	"""Export credentials in KeePass CSV format."""
	from services.extract import export_keepass_csv
	p_print("Exporting to KeePass CSV...", Colours.HEADER)
	try:
		export_keepass_csv()
	except Exception as e:
		p_print(f"Export failed: {e}", Colours.FAIL)
	pause("Press Enter to return to the menu...")


def _action_delete_account(executable_path, config):
	"""Delete a MEGA account and all its files."""
	creds = _pick_credentials(executable_path, config)
	if creds is None:
		return
	if not prompt_yes_no(f"Really delete {creds.email}? This CANNOT be undone."):
		return
	from services.account import delete_account
	if delete_account(creds):
		p_print(f"Account {creds.email} deleted.", Colours.OKGREEN)
		fname = f"credentials/{creds.email.split('@')[0]}.json"
		try:
			os.remove(fname)
			p_print(f"Credential file removed: {fname}", Colours.OKGREEN)
		except OSError:
			pass
	else:
		p_print(f"Failed to delete {creds.email}.", Colours.FAIL)
	pause("Press Enter to return to the menu...")


def _action_change_password(executable_path, config):
	"""Change password for a MEGA account."""
	creds = _pick_credentials(executable_path, config)
	if creds is None:
		return
	new_pw = prompt_text(f"New password for {creds.email}")
	if not new_pw:
		return
	confirm = prompt_text("Confirm new password")
	if new_pw != confirm:
		p_print("Passwords do not match.", Colours.FAIL)
		pause()
		return
	from services.account import change_password
	if change_password(creds, new_pw):
		fname = f"credentials/{creds.email.split('@')[0]}.json"
		try:
			import json
			with open(fname, "r") as f:
				data = json.load(f)
			data["password"] = new_pw
			with open(fname, "w") as f:
				json.dump(data, f, indent=2)
			p_print("Credential file updated.", Colours.OKGREEN)
		except (OSError, json.JSONDecodeError) as e:
			p_print(f"Could not update credential file: {e}", Colours.WARNING)
	pause("Press Enter to return to the menu...")


def _action_create_folder(executable_path, config):
	"""Create a folder in a MEGA account."""
	creds = _pick_credentials(executable_path, config)
	if creds is None:
		return
	name = prompt_text("Folder name")
	if not name:
		return
	from services.account import create_folder
	create_folder(creds, name)
	pause("Press Enter to return to the menu...")


def _open_account_menu(executable_path, config):
	"""Submenu for account management operations."""
	while True:
		items = [
			MenuItem(
				"Delete Account",
				lambda: _action_delete_account(executable_path, config),
				"Remove a MEGA account and all its files",
			),
			MenuItem(
				"Change Password",
				lambda: _action_change_password(executable_path, config),
				"Set a new password for a MEGA account",
			),
			MenuItem(
				"Create Folder",
				lambda: _action_create_folder(executable_path, config),
				"Create a folder in your MEGA cloud",
			),
			MenuItem("Back", lambda: _BACK, "Return to the main menu"),
		]
		menu = Menu("Account Management", items)
		result = menu.run()
		if result is _BACK:
			break


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
				"Account Management",
				lambda: _open_account_menu(executable_path, config),
				"Delete account, change password, create folder",
			),
			MenuItem(
				"Export as Bitwarden CSV",
				_action_export_bitwarden,
				"Password-manager-compatible CSV format",
			),
			MenuItem(
				"Export as 1Password CSV",
				_action_export_onepassword,
				"Password-manager-compatible CSV format",
			),
			MenuItem(
				"Export as KeePass CSV",
				_action_export_keepass,
				"KeePass-compatible CSV format",
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
	sys.exit(0)


def _loop_keepalive(verbose: bool, prune: bool, interval_hours: float):
	"""Run keepalive in a loop every ``interval_hours``."""
	interval_secs = interval_hours * 3600
	p_print(
		f"Keepalive loop: every {interval_hours:.1f}h (Ctrl+C to stop).",
		Colours.HEADER,
	)
	while True:
		keepalive(verbose, prune=prune)
		separator(f"Next run in {interval_hours:.1f}h", Colours.WARNING)
		time.sleep(interval_secs)


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
if console_args.proxy_url and not _proxy_manager.active:
	_proxy_manager.fetch_and_add(console_args.proxy_url)

if __name__ == "__main__":
	set_verbose(console_args.verbose)
	import threading as _th
	_t = _th.Thread(target=auto_update, daemon=True)
	_t.start()
	_t.join(timeout=5)

	executable_path, config = setup()
	set_quiet(config.quiet if config else console_args.quiet)
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
	elif console_args.export_keepass:
		from services.extract import export_keepass_csv
		export_keepass_csv()
	elif console_args.export_bitwarden:
		from services.extract import export_bitwarden_csv
		export_bitwarden_csv()
	elif console_args.export_onepassword:
		from services.extract import export_onepassword_csv
		export_onepassword_csv()
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
				export_jsonl=console_args.export_jsonl,
				provider_name=console_args.provider,
				webhook_url=console_args.webhook_url,
				encryption_password=console_args.encryption_password,
			)
		else:
			loop_registrations(
				console_args.loop,
				executable_path,
				config,
				console_args.visible,
				console_args.attempts,
				console_args.export_csv,
				export_jsonl=console_args.export_jsonl,
				resume=console_args.resume,
				provider_name=console_args.provider,
				webhook_url=console_args.webhook_url,
				encryption_password=console_args.encryption_password,
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
				export_jsonl=console_args.export_jsonl,
				provider_name=console_args.provider,
				webhook_url=console_args.webhook_url,
			)
		)
	else:
		# No flags -> launch the interactive TUI.
		_run_tui(executable_path, config)
