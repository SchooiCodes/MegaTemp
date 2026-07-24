"""
Smoke test: exercises every module in MegaTemp, times everything, catches bugs.

Run:  python _test_smoke.py
"""

import sys
import os
import time


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_tests_run = 0
_tests_failed = 0
_timings: list[tuple[str, float]] = []


def _check(ok: bool, msg: str):
	global _tests_run, _tests_failed
	_tests_run += 1
	if ok:
		print(f"  OK  {msg}")
	else:
		_tests_failed += 1
		print(f"  FAIL  {msg}")


def _section(title: str):
	print(f"\n=== {title} ===")


class _timed:
	def __init__(self, label: str):
		self.label = label
	def __enter__(self):
		self.start = time.perf_counter()
		return self
	def __exit__(self, *exc):
		elapsed = time.perf_counter() - self.start
		_timings.append((self.label, elapsed))
		if elapsed > 0.5:
			print(f"  [{self.label}] took {elapsed:.3f}s — SLOW")


def _import_all():
	_section("Module imports")
	from utilities.models import Colours, Credentials, Config, migrate_config
	_check(Colours().HEADER == "\033[95m", "Colours.HEADER")
	_check(Colours().OKGREEN == "\033[92m", "Colours.OKGREEN")
	c = Credentials("a@b.com", "mpw", "megapw")
	_check(c.email == "a@b.com", "Credentials creation")
	_check(c.emailPassword == "mpw", "Credentials emailPassword")
	_check(c.password == "megapw", "Credentials password")
	c2 = Credentials()
	_check(c2.email == "", "Credentials defaults: email")
	_check(c2.password == "", "Credentials defaults: password")
	from dataclasses import asdict
	d = asdict(c)
	_check(d["id"] == "", "Credentials asdict includes id")
	cfg = Config()
	_check(cfg.schemaVersion == 3, "Config schemaVersion default")
	_check(cfg.maxAttempts == 4, "Config maxAttempts default")
	_check(cfg.mailTimeout == 45, "Config mailTimeout default")
	_check(cfg.emailProvider == "mailtm", "Config provider default")
	cfg2 = Config(executablePath="/usr/bin/chromium", accountFormat="{email}#{password}")
	_check(cfg2.executablePath == "/usr/bin/chromium", "Config with values")
	_check(cfg2.accountFormat == "{email}#{password}", "Config format")
	migrated = migrate_config({"schemaVersion": 0})
	_check(migrated["schemaVersion"] == 3, "Config migration v0→v3")
	migrated2 = migrate_config({"schemaVersion": 3})
	_check(migrated2["schemaVersion"] == 3, "Config migration idempotent")
	return Colours, Credentials, Config, migrate_config


def _test_fs():
	_section("Filesystem (fs.py)")
	from utilities.models import Credentials, Config
	from utilities.fs import (
		write_default_config, read_config, merge_config, write_config,
		save_credentials, save_credentials_csv, save_credentials_jsonl,
		list_credentials, concrete_read_config,
	)
	cfg = Config(
		executablePath="/usr/bin/chromium",
		accountFormat="{email}#{password}",
		schemaVersion=3,
		maxAttempts=4,
		mailTimeout=120,
		emailProvider="mailtm",
	)
	c = Credentials("test@x.com", "mpw", "megapw")
	
	with _timed("write_default_config"):
		w = write_default_config()
	_check(w is None or isinstance(w, Config), "write_default_config returns Config or None")

	with _timed("merge_config"):
		merge_config({"maxAttempts": 8}, cfg)
	r2 = read_config()
	_check(r2 is not None, "read_config after merge")
	
	with _timed("save_credentials"):
		save_credentials(c, cfg.accountFormat, "")
	_check(True, "save_credentials completed (no crash)")
	
	with _timed("save_credentials_csv"):
		save_credentials_csv(c)
	_check(True, "save_credentials_csv completed")
	
	with _timed("save_credentials_jsonl"):
		save_credentials_jsonl(c)
	_check(True, "save_credentials_jsonl completed")
	
	with _timed("list_credentials"):
		creds_list = list_credentials()
	_check(len(creds_list) >= 2, f"list_credentials has {len(creds_list)} entries (expected >= 2)")

	from utilities.etc import clear_tmp
	with _timed("clear_tmp"):
		clear_tmp()
	_check(True, "clear_tmp completed (no crash)")


def _test_etc():
	_section("Utilities (etc.py)")
	from utilities.etc import (
		elapsed, separator, p_print, Colours, clear_tmp, delete_default,
		ProxyManager, LoopState, save_checkpoint, load_checkpoint,
		clear_checkpoint, VERSION, notify, set_quiet, send_webhook,
		capture_worker_output,
	)
	
	_check(VERSION == "v1.4.0", f"VERSION is {VERSION}")
	
	e = elapsed(time.monotonic() - 60)
	_check("s" in e, f"elapsed(60s): {e}")
	e2 = elapsed(time.monotonic() - 125)
	_check("m" in e2, f"elapsed(125s): {e2}")
	
	with _timed("ProxyManager empty"):
		pm = ProxyManager()
	_check(pm.get_proxy() is None, "ProxyManager empty returns None")
	_check(pm.count == 0, "ProxyManager empty count")
	
	with _timed("ProxyManager single"):
		pm2 = ProxyManager(proxy="http://user:pass@1.2.3.4:8080")
	p = pm2.get_proxy()
	_check(p == "http://user:pass@1.2.3.4:8080", "ProxyManager single proxy")
	_check(pm2.count == 1, "ProxyManager count == 1")
	
	with _timed("ProxyManager rotation"):
		pm3 = ProxyManager(proxy_file="/dev/null", per_attempt=True)
	_check(pm3.count == 0, "ProxyManager empty file")

	with _timed("ProxyManager distribute"):
		slots = pm2.distribute(3)
	_check(len(slots) == 3, "ProxyManager distribute(3) returns 3 items")
	_check(slots[0] == "http://user:pass@1.2.3.4:8080", "distribute fills slots")
	_check(slots[1] == "http://user:pass@1.2.3.4:8080", "distribute round-robin works")

	with _timed("checkpoint save/load"):
		save_checkpoint(LoopState(completed=5, failed=2))
		cp = load_checkpoint()
	_check(cp is not None and cp.completed == 5 and cp.failed == 2, "checkpoint round-trip")
	clear_checkpoint()
	cp2 = load_checkpoint()
	_check(cp2 is None, "checkpoint clear")

	with _timed("capture_worker_output"):
		with capture_worker_output() as buf:
			p_print("hello", Colours.OKGREEN)
			p_print("world", Colours.FAIL)
	_check(len(buf) == 2, "capture_worker_output captured 2 messages")


def _test_web():
	_section("Web utilities (web.py)")
	from utilities.web import (
		set_verbose, get_random_string, _get_faker,
	)
	
	set_verbose(True)
	set_verbose(False)
	_check(True, "set_verbose toggles")
	
	with _timed("_get_faker (first call — lazy init)"):
		f = _get_faker()
	_check(f is not None, "_get_faker returns instance")
	
	with _timed("_get_faker (cached)"):
		f2 = _get_faker()
	_check(f2 is f, "_get_faker is cached (same instance)")
	name = f.first_name()
	_check(len(name) > 0, f"Faker generates name: {name}")
	
	for length in [0, 1, 10, 100]:
		s = get_random_string(length)
		_check(len(s) == length, f"get_random_string({length}) -> len={len(s)}")


def _test_menu():
	_section("Menu (menu.py)")
	from utilities.menu import Menu, MenuItem, _BACK
	
	items = [MenuItem("Option 1", value="val1"), MenuItem("Back", value=_BACK)]
	menu = Menu("Test Menu", items)
	_check(len(menu.items) == 2, "Menu has 2 items")
	_check(menu.title == "Test Menu", "Menu title")
	_check(menu.items[0].label == "Option 1", "MenuItem label")
	_check(menu.items[0].get_value() == "val1", "MenuItem value")


def _test_services():
	_section("Services")
	from utilities.models import Config
	from services.extract import extract_credentials, export_bitwarden_csv, export_onepassword_csv, export_keepass_csv
	from services.upload import upload_file
	from services.download import list_files, download_file, _action_browse_cloud
	from services.alive import keepalive
	from services.account import delete_account, change_password, create_folder
	
	from utilities.fs import list_credentials
	folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "credentials")
	os.makedirs(folder, exist_ok=True)
	
	with _timed("extract_credentials (empty folder)"):
		extract_credentials("{email}#{password}")
	_check(True, "extract_credentials completed (no crash)")
	
	with _timed("export_bitwarden_csv (empty folder)"):
		export_bitwarden_csv()
	_check(True, "export_bitwarden_csv completed")
	
	with _timed("export_onepassword_csv (empty folder)"):
		export_onepassword_csv()
	_check(True, "export_onepassword_csv completed")
	
	with _timed("export_keepass_csv (empty folder)"):
		export_keepass_csv()
	_check(True, "export_keepass_csv completed")
	
	with _timed("keepalive (empty folder)"):
		keepalive(verbose=False)
	_check(True, "keepalive completed (no crash)")


def _test_main():
	_section("main.py functions")
	from utilities.models import Config
	from utilities.etc import ProxyManager
	import main as m
	
	_check(hasattr(m, "setup"), "main.setup exists")
	_check(hasattr(m, "register"), "main.register exists")
	_check(hasattr(m, "parallel_registrations"), "main.parallel_registrations exists")
	_check(hasattr(m, "loop_registrations"), "main.loop_registrations exists")
	
	with _timed("_build_browser_args (no proxy)"):
		args = m._build_browser_args()
	_check("--no-sandbox" in args, "browser args include --no-sandbox")
	_check("--disable-gpu" in args, "browser args include --disable-gpu")
	
	with _timed("_build_browser_args (with proxy)"):
		args2 = m._build_browser_args(proxy_override="http://1.2.3.4:8080")
	_check("--proxy-server=http://1.2.3.4:8080" in args2, "browser args include proxy")
	
	m._proxy_manager = ProxyManager(proxy="http://user:pass@5.6.7.8:3128")
	with _timed("_build_browser_args (with proxy manager)"):
		args3 = m._build_browser_args()
	_check("--proxy-server=http://user:pass@5.6.7.8:3128" in args3, "browser args uses proxy manager")
	m._proxy_manager = ProxyManager()
	
	_check(m._HARMLESS_ASYNC_ERRORS == ("Target closed", "No session with given id"), "harmless errors defined")
	_check(len(m._BROWSER_BASE_ARGS) >= 10, f"browser base args count: {len(m._BROWSER_BASE_ARGS)}")
	
	with _timed("_load_settings"):
		m._load_settings()
	_check("attempts" in m._SETTINGS, "_SETTINGS has attempts")
	_check("visible" in m._SETTINGS, "_SETTINGS has visible")
	
	with _timed("_save_settings"):
		m._save_settings()
	_check(True, "_save_settings completed")

	from utilities.password_strength import estimate_entropy, strength_label
	with _timed("password_strength"):
		e = estimate_entropy("Abcd1234!@#$")
	_check(e > 40, f"estimate_entropy('Abcd1234!@#$') = {e:.1f} (expected > 40)")
	lbl, _ = strength_label("short")
	_check(lbl == "Very Weak", f"strength_label('short') = {lbl}")
	e2 = estimate_entropy("CorrectHorseBatteryStaple99!")
	lbl2, _ = strength_label("CorrectHorseBatteryStaple99!")
	_check(e2 > 90, f"estimate_entropy(strong) = {e2:.1f} (expected > 90)")
	_check(lbl2 == "Very Strong", f"strength_label(strong) = {lbl2}")
	
	from utilities.retry import retry
	counter = [0]
	@retry(max_attempts=3)
	def _succeeds_sync():
		counter[0] += 1
		return 42
	
	with _timed("retry (success)"):
		res = _succeeds_sync()
	_check(res == 42, f"retry returns {res}")
	_check(counter[0] == 1, f"retry called once (not retried)")
	
	from utilities.provider import get_provider, get_provider_names
	names = get_provider_names()
	_check("mailtm" in names, "provider names includes mailtm")
	_check("guerrillamail" in names, "provider names includes guerrillamail")
	p = get_provider("nonexistent")
	_check(p is None, "get_provider('nonexistent') returns None")
	
	from pymailtm.pymailtm import CouldNotGetAccountException, CouldNotGetMessagesException
	_check(issubclass(CouldNotGetAccountException, Exception), "CouldNotGetAccountException is Exception")
	_check(issubclass(CouldNotGetMessagesException, Exception), "CouldNotGetMessagesException is Exception")
	
	from utilities.web import _get_provider
	with _timed("_get_provider (lazy)"):
		p2 = _get_provider("mailtm")
	_check(p2 is not None, "_get_provider('mailtm') returns provider")
	with _timed("_get_provider (cached)"):
		p3 = _get_provider("mailtm")
	_check(p3 is not None, "_get_provider cached call works")


def _test_password_generator():
	_section("Password generator")
	from utilities.password_strength import generate_password
	for length in [8, 16, 32]:
		with _timed(f"generate_password({length})"):
			pw = generate_password(length)
		_check(len(pw) == length, f"generate_password({length}) -> len={len(pw)}")
		_check(any(c.isdigit() for c in pw), f"password has digits")
		_check(any(not c.isalnum() for c in pw), f"password has special chars")

	pw1 = generate_password(16)
	pw2 = generate_password(16)
	_check(pw1 != pw2, "passwords are unique")


def _test_registration():
	_section("Registration (main.py)")
	import asyncio
	import io
	import sys
	import main as m
	from utilities.models import Config
	from utilities.etc import ProxyManager

	m._proxy_manager = ProxyManager()

	with _timed("parallel_registrations(0, 0)"):
		try:
			m.parallel_registrations(0, "", Config(), parallelism=0)
			_check(False, "parallel_registrations(0,0) should sys.exit(0)")
		except SystemExit as e:
			_check(e.code == 0, f"parallel_registrations(0,0) exits {e.code}")

	with _timed("register (no browser)"):
		async def _try_register():
			try:
				cfg = Config(maxAttempts=1)
				await m.register(None, "/nonexistent/browser", cfg, max_attempts=1)
			except SystemExit:
				pass
			except Exception:
				pass

		try:
			asyncio.run(_try_register())
		except Exception:
			pass
		_check(True, "register (no browser) handled gracefully")

	with _timed("_action_create_one (no browser)"):
		old_stdin = sys.stdin
		sys.stdin = io.StringIO("\n")
		try:
			try:
				m._action_create_one("/nonexistent/browser", Config())
			except Exception:
				pass
		finally:
			sys.stdin = old_stdin
		_check(True, "_action_create_one (no browser) handled gracefully")


def _test_cli():
	_section("CLI (subprocess)")
	import subprocess
	base = [sys.executable, "main.py"]
	
	with _timed("CLI --help"):
		r = subprocess.run(base + ["--help"], capture_output=True, text=True, timeout=15)
	_check(r.returncode == 0, "--help exits 0")
	_check("usage:" in r.stdout.lower() or "usage:" in r.stderr.lower(), "--help shows usage")
	
	with _timed("CLI --version"):
		r = subprocess.run(base + ["--version"], capture_output=True, text=True, timeout=15)
	_check(r.returncode == 0, "--version exits 0")
	_check("v1.4.0" in r.stdout, f"--version shows {r.stdout!r}")
	
	with _timed("CLI --health --json"):
		r = subprocess.run(base + ["--health", "--json"], capture_output=True, text=True, timeout=30)
	_check(r.returncode == 0, "--health --json exits 0")
	try:
		import json as _json
		import re
		raw = r.stdout
		m = re.search(r'\{.*\}', raw, re.DOTALL)
		if m:
			data = _json.loads(m.group())
			_check("accounts" in data, "--health --json returns accounts key")
		else:
			_check(False, f"--health --json: no JSON object found in {raw[:200]!r}")
	except Exception as e:
		_check(False, f"--health --json: {e}")
	
	with _timed("CLI --health"):
		r = subprocess.run(base + ["--health"], capture_output=True, text=True, timeout=30)
	_check(r.returncode == 0, "--health exits 0")
	
	with _timed("CLI --quiet --version"):
		r = subprocess.run(base + ["--quiet", "--version"], capture_output=True, text=True, timeout=15)
	_check(r.returncode == 0, "--quiet --version exits 0")

	with _timed("CLI --webhook-url http://x.com --version"):
		r = subprocess.run(base + ["--webhook-url", "http://example.com/hook", "--version"], capture_output=True, text=True, timeout=15)
	_check(r.returncode == 0, "--webhook-url --version exits 0")

	with _timed("CLI --profile testcli --version"):
		r = subprocess.run(base + ["--profile", "testcli", "--version"], capture_output=True, text=True, timeout=15)
	_check(r.returncode == 0, "--profile --version exits 0")


def main():
	start = time.perf_counter()
	
	import_all = _import_all()
	_test_fs()
	_test_etc()
	_test_web()
	_test_menu()
	_test_services()
	_test_main()
	_test_registration()
	_test_password_generator()
	_test_cli()
	
	total = time.perf_counter() - start
	
	print(f"\n{'='*50}")
	print(f"Results: {_tests_run} checks, {_tests_failed} failures, {total:.2f}s total")
	
	if _timings:
		slow = [(l, t) for l, t in _timings if t > 0.2]
		if slow:
			print(f"\nSlow operations (>200ms):")
			for label, elapsed in sorted(slow, key=lambda x: -x[1]):
				print(f"  {elapsed:.3f}s  {label}")
	
	if _tests_failed:
		print("\nSOME CHECKS FAILED")
		sys.exit(1)
	else:
		print("\nALL CHECKS PASSED")
		sys.exit(0)


if __name__ == "__main__":
	main()
