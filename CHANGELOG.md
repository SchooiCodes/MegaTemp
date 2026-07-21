# Changelog

All notable changes to MegaTemp are documented here. This project adheres to
[Semantic Versioning](https://semver.org/).

## [v1.3.0] - 2026-07-21

### Added
- **Proxy support** — `--proxy URL`, `--proxy-file path`, `--proxy-per-attempt`
  CLI flags for IP rotation. `ProxyManager` class handles rotation, validation,
  and file-based loading.
- **Parallel loop mode** — `--parallel N` / `-j N` flag launches multiple
  Chromium workers concurrently, each with its own browser and optional proxy
  (~N× throughput for mass generation).
- **Config schema versioning** — `Config.schemaVersion` with migration path
  from older configs. New fields: `proxy`, `proxyFile`, `proxyPerAttempt`,
  `maxAttempts`, `csvExport`, `visibleBrowser`, `emailProvider`.
- **Settings persistence** — session settings (`maxAttempts`, `visibleBrowser`,
  `csvExport`) now save to `config.json` and restore on restart.
- **Config editor in TUI** — Settings → Edit Config lets you change
  `executablePath`, `accountFormat`, and proxy URL interactively.
- **Loop checkpoint/resume** — `--resume` flag recovers interrupted batches
  from a `loop_state.json` checkpoint (saved after every iteration).
- **Keepalive upgrade** — per-account retries with exponential backoff,
  summary table (status, quota, age), and `--prune` flag to auto-delete dead
  accounts.
- **Enhanced credentials viewer** — interactive mode with `[p]` reveal
  passwords, `[d]` delete individual accounts, up/down navigation.
- **Confirmation summaries** — before mass loops, shows estimated time and
  settings summary, asks for confirmation.
- **Keyboard shortcuts in menus** — `1`-`9` jump to items, `Ctrl+C` returns
  to menu gracefully.
- **Browser auto-download** — Settings → Download Chromium runs
  `pyppeteer install` and auto-configures the path.
- **Graceful Ctrl+C** — signal handler prevents traceback dumps.
- **mail.tm session reuse** — cached account is reused across retries
  (saves a disposable inbox on transient MEGA failures).
- **Email provider abstraction** — `utilities/provider.py` defines the
  `EmailProvider` ABC for future backend support.
- **Expanded browser detection** — added NixOS, Flatpak, Snap, Homebrew,
  macOS `.app` bundle, and `%LOCALAPPDATA%` paths.

### Added (post-v1.3.0-tag — code quality)
- **`separator()` deduplication** — removed local copies from `alive.py` and
  `download.py`; all share the single import from `utilities.etc`.
- **Dead code removal** — unreachable duplicate body in `_action_upload_dir`
  stripped (~30 lines).
- **`ProxyManager.distribute(count)`** — public method replaces private
  `_proxies` attribute access in `parallel_registrations`.
- **Parallel worker robustness** — catches `Exception` (not just `SystemExit`)
  so one failed worker doesn't kill the entire parallel batch.
- **`setup.sh` config alignment** — default config now matches runtime
  `write_default_config()` output.

### Added (post-v1.3.0-tag — new features)
- **Guerrilla Mail provider** — `utilities/guerrilla.py` implements the
  `EmailProvider` ABC for disposable emails with no signup required.
- **Provider registry** — `register_provider()`, `get_provider()`,
  `get_provider_names()`; built-in mailtm and guerrillamail auto-register.
- **Provider dispatch in registration flow** — `generate_mail()`,
  `mail_login()`, `get_mail()` all accept a `provider_name` parameter and
  route through the `EmailProvider` ABC for non-mail.tm providers.
- **Account notes/tags** — `Credentials.notes` and `Credentials.tags` fields;
  viewer shows them inline; `[n]` to edit notes, `[t]` to edit tags.
- **Password strength estimation** — `utilities/password_strength.py` with
  entropy-based strength labels shown in the credentials viewer.
- **Email provider ABC** — concrete `MailTmProvider` and
  `GuerrillaMailProvider` implementations; both auto-register on import.

### Added (post-v1.3.0-tag — QoL)
- **Health dashboard** — upgraded Storage Info: ✓/✗ status, quota, age, tags
  per account with alive/dead summary.
- **Scheduled keepalive** — `--interval HOURS` flag loops keepalive every N
  hours with configurable interval.
- **Search in credentials viewer** — `[/]` key filters accounts by
  email/notes/tags; `[Esc]` clears filter.
- **Batch delete in viewer** — `[a]` key deletes all visible (filtered)
  accounts with one press.
- **Upload progress bar** — animated `[████░░░░] 60%` bar replaces the simple
  spinner, showing file size and elapsed time.
- **Config validation on load** — warns about non-existent executablePath,
  improbable maxAttempts, or malformed proxy URLs.
- **Desktop notifications** — `notify()` function uses `notify-send` (Linux),
  `osascript` (macOS), or PowerShell (Windows); fires on loop completion.
- **Network retry wrapper** — `utilities/retry.py` with `@retry` decorator
  (exponential backoff, tenacity-based when available); applied to MEGA login.
- **Cloud file browser** — `Browse Cloud` TUI option lists files in the most
  recent account and offers download to a local directory.
- **CLI cloud flags** — `--list-cloud`, `--download-cloud FILE_ID`,
  `--download-dest DIR`.
- **Account picker for uploads** — both `Upload File` and `Upload Directory`
  now show a numbered list of saved accounts to choose from.

### Added (post-v1.3.0-tag — tab completion & CLI)
- **Tab completion for file paths** — `prompt_path()` in `menu.py` with
  `readline`-based Tab completion; used in upload/download interactive prompts.
- **`--version` flag** — displays `MegaTemp v1.3.0` and exits immediately
  (no setup required).
- **`--provider NAME` CLI flag** — selects email provider (`mailtm` or
  `guerrillamail`) from headless/scripted invocations; threaded through
  `register()`, `loop_registrations()`, and `parallel_registrations()`.
- **`--health` CLI flag** — show storage health dashboard from the command line
  (previously TUI-only).
- **`--health --json`** — machine-readable JSON output with per-account status,
  quota, age, and summary.
- **Provider validation at CLI** — `--provider bad-name` errors immediately
  with list of valid providers.
- **`docker-compose.yml`** — one-command Docker Compose setup with volume
  mounts for credential persistence and TTY allocation for interactive mode.
- **Makefile** — common dev commands (`make run`, `make test`, `make lint`,
  `make format`, `make clean`, `make release`).
- **`.editorconfig`** — consistent editor settings for tab/space/encoding.

### Added (post-v1.3.0-tag — packaging)
- **Dockerfile** — `python:3.12-slim` with Chromium + MegaTemp.
- **pre-commit hook** — `.githooks/pre-commit` runs `ruff check` + `ruff format`.
- **Setup script** — `setup.sh` for one-command dev environment setup.

### Fixed
- `@dataclass` import missing in `etc.py` on fresh module load.
- Syntax error in CLI dispatch after keepalive/prune merge.
- `--upload-dir` was not triggering the explicit-flags branch in CLI dispatch.
- Parallel worker semaphore not held across `register()` call (all N workers
  could launch simultaneously).
- `TimeoutExpired.stdout` bytes decoding in CLI tests (TypeError on substring check).
- Unused imports cleaned across `main.py` and test file.

### Tests
- 74 tests (was 68) — added download module tests (list_files, download_file
  error handling, separator, --list-cloud, --download-cloud CLI tests).
- 91 tests (was 84) — added config validation, edge case, and menu tests.
- 94 tests (was 91) — added prompt_path, prompt_text lifecycle tests, version
  flag test coverage.
- 98 tests (was 94) — added provider validation, health flag, JSON output tests.
- 99 tests (was 98) — added --health --json output structure test.
- 100 tests (was 99) — added --json guard (requires --health) and expanded provider validation.
- All existing tests preserved.

## [v1.2.0] - 2026-07-21

### Added
- **Auto-update system** for the frozen EXE — checks GitHub Releases on
  startup, prompts to install, downloads with progress, replaces binary,
  and restarts automatically.
- Browser reuse in loop mode — Chromium launches once instead of per-iteration
  (~30-40s faster for 5 accounts).
- Upload retry prompt — after "File not found", offers to try a different path.
- Exit confirmation — "Are you sure?" before quitting the TUI.
- Export overwrite warning — prompts before replacing an existing
  `credentials.txt`.
- Auto-generated GitHub Releases — pushing a tag like `v1.2.0` builds
  Linux/Windows/macOS executables and attaches them to a release automatically.

### Optimized
- **Parallel email generation** — the first mail.tm inbox is created while
  Chromium launches instead of waiting for the browser to finish first
  (~1-2s saved per account, no risk since both operations are async).
- **Background `delete_default()`** — the MEGA API call to remove the welcome
  file now runs in a background thread while credentials are saved and files
  uploaded; falls back silently if it outruns the 5s budget (~3-5s saved).
- **Faster typing in MEGA forms** — `_robust_type` delays reduced (sleep 0.3→0.1,
  per-char 50→25ms) with the verify step preserved so reliability is unchanged
  (~1-2s saved).
- **Zero initial delay before mail polling** — the hard 1.5s sleep between form
  submission and first mail check was removed; polling starts immediately (~1.5s
  saved when MEGA sends the email fast).
- **Faster mail polling** — poll interval 1.5→1.0s, max attempts increased to
  120 (same 2min timeout) (~0.5s saved per poll cycle).
- **Lazy Faker init** — Faker locale data is now loaded on first use instead of
  at module import time (~0.2s faster startup).
- **Browser launch flags** — added `--no-first-run`, `--disable-background-
  networking`, `--disable-sync` to shave ~1s off Chromium startup.
- **Removed redundant `clear_tmp()` from loop body** — already cleaned once
  before the loop; calling it again with a shared browser user-data-dir was
  both wasteful and unsafe (~0.5s per iteration).

**Estimated total speedup: ~8-13s per account (35-50% faster).**

### Fixed
- **`asyncio.coroutine` crash in Windows EXE** — `mega.py` pins tenacity 5.x
  which uses the removed `@asyncio.coroutine` decorator. Build now forces
  `tenacity>=9.0.0` and a runtime shim is added as a safety net.
- **`termios` crash on Windows source install** — `menu.py` imported `tty`/`termios`
  at module level. Now deferred with a `msvcrt` fallback for Windows keyboard input.
- **Windows EXE asset name** — release now includes `MegaTemp-windows.exe`
  (with `.exe`) so it downloads ready-to-run.
- **Loop summary always showed 0 successful / X failed** — `register()` called
  `sys.exit(0)` on success in TUI mode, and `loop_registrations` counted every
  `SystemExit` as a failure. Now checks the exit code.
- **NameError: `_unique_mail_address(domains)` used undefined variable** —
  `domains` was never assigned in `generate_mail()`. Changed to the global
  `_mailtm_domains`.
- **Upload path with `~` not expanded** — added `os.path.expanduser()`.
- **Import-time crash from module-level `Mega()`** — moved instantiation into
  the functions that need it (`delete_default`, `keepalive`).
- **PyInstaller build failed on Windows** — `2>/dev/null` is bash syntax, but
  Windows runners use PowerShell. Added `shell: bash` to the install step.
- **PyInstaller build failed from `pathlib` conflict** — `mega.py>=1.0.8`
  depends on the obsolete `pathlib==1.0.1` backport which conflicts with
  PyInstaller on Python 3.12+. Workflow now uninstalls it before building.
- **Ruff format CI was failing** — code changes introduced whitespace that
  didn't match ruff's style. Ran `ruff format` to align.

### Changed
- **mail.tm address generation** — now uses high-entropy random strings
  (`mt` + 12 random chars) instead of `random_username` common words. Drastically
  reduces HTTP 422 "already used" collisions (was taking ~14 attempts, now ~1).
- **Faster mail.tm retry backoff** — jittered 0.3-1.5s instead of linear up to
  5s.
- **Cached mail.tm domain list** — fetched once and reused across retries
  instead of re-fetching on every attempt.
- Renamed `utilities/types.py` → `utilities/models.py` (shadows stdlib `types`).
- Removed `Credentials.__getitem__`/`__delitem__` (unbound `dict` methods on a
  dataclass caused `TypeError`).
- `clear_tmp()` now retries after killing lock-holders (was `max_attempts=1`).
- `reinstall_tenacity` uses `sys.executable` instead of bare `python` for venv
  safety.

### Tests
- Added comprehensive 52-test suite covering models, fs, etc, web, menu,
  extract, upload, and main modules (pytest, temp-dir isolated).

## [v1.1.0] - 2026-07-20

### Added
- Interactive **terminal menu** (zero-dependency, arrow-key navigation) that
  launches by default when `main.py` is run with no arguments.
- `--visible` / `-sh` flag to run Chromium in a visible (non-headless) window.
- `--attempts N` / `-a N` flag to cap registration retries (default 4).
- `--export-csv` / `-csv` flag to also append every account to
  `credentials/accounts.csv`.
- In-place status line for the mail-confirmation polling so the console stays
  clean.
- Loop-mode summary: success/failure counts, total and average time.
- Elapsed-time reporting per registration (`Account verified in Ns.`).
- Benign pyppeteer teardown warnings are now suppressed.

### Fixed
- Robust email/password entry (`_robust_type`) — MEGA's custom inputs drop the
  first keystroke; dead accounts ("invalid email or password") are no longer
  created.
- Bounded retry loops for mail generation and confirmation polling (no more
  infinite hangs).
- TUI border alignment and escape-sequence handling (arrow keys no longer exit
  the menu).

## [v1.0.0] - 2026-07-19

### Added
- Working MEGA account generation via mail.tm + headless Chromium.
- File upload with optional public share link.
- Keepalive service that logs into saved accounts.
- Credential export with a configurable `accountFormat`.
- Repo hygiene: GPL-3.0 license, CODE_OF_CONDUCT, CONTRIBUTING, SECURITY,
  issue/PR templates, and a Ruff CI workflow.
- Forked from [qtchaos/py_mega_account_generator](https://github.com/qtchaos/py_mega_account_generator).
