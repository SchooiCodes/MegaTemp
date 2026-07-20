# Changelog

All notable changes to MegaTemp are documented here. This project adheres to
[Semantic Versioning](https://semver.org/).

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
