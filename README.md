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
| **Parallel mode** | `python main.py -l 50 -j 5` (5 concurrent workers) |
| **Proxy rotation** | `python main.py -l 20 --proxy-file proxies.txt` |
| **Resume batches** | `python main.py -l 20 --resume` (recover interrupted runs) |
| **File upload** | `python main.py -f photo.jpg -p` (uploads + public link) |
| **Directory upload** | Menu → *Upload Directory* + account picker |
| **Keep accounts alive** | `python main.py -ka --prune` (logs in, removes dead accounts) |
| **Scheduled keepalive** | `python main.py -ka --interval 24` (runs every 24h) |
| **Export credentials** | Menu → *Export Credentials*, or `python main.py -e` |
| **Disposable email** | [mail.tm](https://mail.tm) or **Guerrilla Mail** — no real email needed |
| **Choose provider** | `python main.py --provider guerrillamail` (CLI) or config `emailProvider` |
| **Headless browser** | Pyppeteer + Chromium (watch it with `-sh`) |
| **Custom format** | `config.json` → `accountFormat: "{email}#{password}"` |
| **Config editor** | Menu → *Settings → Edit Config* |
| **Config validation** | Warns on bad paths, improbable values, proxy format on load |
| **Prebuilt binaries** | [Releases](https://github.com/SchooiCodes/MegaTemp/releases) — no Python required |
| **Auto-update** | Frozen EXE checks for new releases on startup |
| **Cloud browser** | Menu → *Browse Cloud* — list + download cloud files |
| **CLI cloud access** | `--list-cloud`, `--download-cloud ID`, `--download-dest DIR` |
| **Health dashboard** | Menu → *Storage Info* — per-account status, quota, age |
| **Account notes/tags** | Menu → *View Credentials* — press `n` for notes, `t` for tags |
| **Search accounts** | Menu → *View Credentials* — press `/` to filter |
| **Batch delete** | Menu → *View Credentials* — press `a` to delete all filtered |
| **Password strength** | Viewer shows strength label when passwords are revealed |
| **Desktop notifications** | On loop/parallel completion (Linux, macOS, Windows) |
| **Upload progress bar** | Animated `[████░░░░] 60%` during file upload |
| **Tab completion** | Press Tab when entering file paths in upload/download prompts |
| **Docker support** | `docker build -t megatem . && docker run -it megatem` |
| **Docker Compose** | `docker compose up` with persistent credentials |
| **Makefile** | `make run`, `make test`, `make lint`, `make format`, `make clean` |

---

## TUI (Interactive Menu)

Run without arguments:

```
MegaTemp v1.3.0
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
| `--prune` | With `-ka`, delete credential files for failed accounts |
| `--interval <h>` | With `-ka`, loop continuously every N hours |
| `-v` | Verbose logging |
| `-sh` | Show the Chromium window (non-headless) |
| `-csv` | Also export each account to `credentials/accounts.csv` |
| `--export-jsonl` | Also export to `credentials/accounts.jsonl` |
| `--proxy <url>` | Single proxy URL (rotation on each attempt) |
| `--proxy-file <path>` | File with one proxy URL per line |
| `--proxy-per-attempt` | Rotate proxy on every registration attempt |
| `--resume` | Resume an interrupted `--loop` batch |
| `-j <n>` | Concurrent workers for `--loop` (default 1) |
| `--list-cloud` | List files in the most recent MEGA account |
| `--download-cloud <id>` | Download a cloud file by its node ID |
| `--download-dest <dir>` | Destination for `--download-cloud` (default `.`) |
| `--upload-dir <dir>` | Upload all files in a directory |
| `--version` | Show version and exit |
| `--provider <name>` | Email provider: `mailtm` or `guerrillamail` |
| `--health` | Show health dashboard (quota, age, status) from CLI |

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
