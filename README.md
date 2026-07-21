# MegaTemp

> Generate MEGA.nz accounts from the command line — disposable email, headless
> browser, file upload, and loops.

[![Ruff](https://github.com/SchooiCodes/MegaTemp/actions/workflows/ruff.yml/badge.svg)](https://github.com/SchooiCodes/MegaTemp/actions/workflows/ruff.yml)
[![Build](https://github.com/SchooiCodes/MegaTemp/actions/workflows/build.yml/badge.svg)](https://github.com/SchooiCodes/MegaTemp/actions/workflows/build.yml)

---

## ⚠️ Disclaimer

**For educational and personal-automation purposes only.** Automated account
creation may violate [MEGA's Terms of Service](https://mega.nz/terms). Use at
your own risk.

---

## Quick start

```bash
git clone https://github.com/SchooiCodes/MegaTemp.git
cd MegaTemp
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python main.py
```

- Chromium (or Chrome, Brave, Edge) must be installed. If not auto-detected,
  you'll be prompted for the path on first run.
- Full docs: [`docs/`](./docs/)

---

## Features

| Feature | How |
|---------|-----|
| **Single account** | `python main.py` — opens the interactive TUI menu |
| **Mass generation** | Menu → *Loop Create*, or `python main.py -l 10` |
| **File upload** | `python main.py -f photo.jpg -p` (uploads + public link) |
| **Keep accounts alive** | `python main.py -ka` (logs into every saved account) |
| **Export credentials** | Menu → *Export Credentials*, or `python main.py -e` |
| **Disposable email** | [mail.tm](https://mail.tm) inboxes — no real email needed |
| **Headless browser** | Pyppeteer + Chromium (watch it with `-sh`) |
| **Custom format** | `config.json` → `accountFormat: "{email}#{password}"` |
| **Prebuilt binaries** | [Releases](https://github.com/SchooiCodes/MegaTemp/releases) — no Python required |

---

## TUI (Interactive Menu)

Run without arguments:

```
MegaTemp v1.2.0
╔══════════════════════════════════════════════════════╗
║  Create Account                                      ║
║  Loop Create                                         ║
║  View Credentials                                    ║
║  Export Credentials                                  ║
║  Keep Alive Accounts                                 ║
║  Upload File                                         ║
║  Settings                                            ║
║  Exit                                                ║
╚══════════════════════════════════════════════════════╝
```

**↑ ↓** navigate · **Enter** select · **Esc** back/exit

Settings (per-session): max retries, visible browser, CSV export toggle.

---

## CLI Reference

| Flag | Description |
|------|-------------|
| `-f <path>` | Upload a file to the new account |
| `-p` | Public share link for the uploaded file |
| `-l <n>` | Loop `n` times (prints summary) |
| `-a <n>` | Max registration attempts per account (default 4) |
| `-e` | Export all saved credentials to one file |
| `-ka` | Log into all accounts to keep them alive |
| `-v` | Verbose logging |
| `-sh` | Show the Chromium window (non-headless) |
| `-csv` | Also export each account to `credentials/accounts.csv` |

> **Don't** combine services (`-e`, `-ka`) with upload (`-f`, `-p`).

---

## Credentials

Saved to `credentials/` folder. Default is one JSON file per account:

```json
{"email": "user@web-library.net", "emailPassword": "abc123", "password": "xyz789"}
```

- `email` / `password` — your MEGA login
- `emailPassword` — password for the disposable mail.tm inbox

Set `accountFormat` in `config.json` for custom output (e.g.
`"{email}#{password}"`).

---

## Installation details

See [Installation](docs/Installation.md) for:
- Virtual environment setup
- Browser configuration
- Building standalone executables

---

## Changelog

See [CHANGELOG.md](./CHANGELOG.md).

---

## License

**GNU General Public License v3.0** — see [LICENSE](./LICENSE).

Forked from [qtchaos/py_mega_account_generator](https://github.com/qtchaos/py_mega_account_generator).
