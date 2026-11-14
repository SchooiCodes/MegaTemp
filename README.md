# MegaTemp

**Create MEGA.nz accounts from your terminal — automatically.** MegaTemp drives a
headless Chromium, signs up with a disposable inbox, confirms the email, and
saves the credentials for you. It can also upload files, download from the
cloud, keep accounts alive, and export everything to your password manager.

[![Tests](https://github.com/SchooiCodes/MegaTemp/actions/workflows/tests.yml/badge.svg)](https://github.com/SchooiCodes/MegaTemp/actions/workflows/tests.yml)
[![Ruff](https://github.com/SchooiCodes/MegaTemp/actions/workflows/ruff.yml/badge.svg)](https://github.com/SchooiCodes/MegaTemp/actions/workflows/ruff.yml)
[![Build](https://github.com/SchooiCodes/MegaTemp/actions/workflows/build.yml/badge.svg)](https://github.com/SchooiCodes/MegaTemp/actions/workflows/build.yml)
[![License](https://img.shields.io/badge/License-GPL--3.0-blue.svg)](./LICENSE)

---

## ⚠️ Disclaimer

**For educational and personal-automation purposes only.** Automated account
creation may violate [MEGA's Terms of Service](https://mega.nz/terms). You are
responsible for how you use it and for the accounts you create.

---

## Install

You need **Chromium, Chrome, Brave, or Edge** installed. MegaTemp finds it
automatically; if it can't, it asks once and remembers the path.

### Option A — prebuilt binary (no Python needed)

Download from [Releases](https://github.com/SchooiCodes/MegaTemp/releases/latest):

| Platform | File |
|---|---|
| Windows | `MegaTemp-windows.exe` |
| Linux | `MegaTemp-linux` |
| macOS | `MegaTemp-macos` |

Run it (on Linux/macOS, `chmod +x` first). Frozen builds can check for updates
with `MegaTemp --update`.

### Option B — from source

Python **3.11+** (tested on 3.11–3.14).

```bash
git clone https://github.com/SchooiCodes/MegaTemp.git
cd MegaTemp

python -m venv venv
# Windows: venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

pip install -r requirements.txt
python main.py
```

> **Windows note:** if your console uses a legacy code page, MegaTemp switches
> to ASCII automatically. Force it with `set MEGATEMP_ASCII=1`, disable colour
> with `set NO_COLOR=1`.

---

## Your first account

```bash
python main.py
```

The interactive menu opens. Choose **Create Account** and watch the log.

What happens behind the scenes:

1. A disposable inbox is created ([mail.tm](https://mail.tm), or Guerrilla Mail).
2. Chromium opens MEGA's sign-up page and fills it in.
3. MegaTemp waits for the confirmation email and follows the link.
4. The login is saved to `credentials/` as JSON.

The first run also writes `config.json` with defaults. Nothing is sent anywhere
except to MEGA, your email provider, and any proxy/webhook you configure.

---

## Common tasks

| I want to… | Command |
|---|---|
| Create one account | `python main.py` |
| Create 20 accounts | `python main.py -l 20` |
| Create 50 accounts with 5 browsers | `python main.py -l 50 -j 5` |
| Use a different email provider | `python main.py --provider guerrillamail` |
| Upload a file and get a public link | `python main.py -f photo.jpg -p` |
| Upload every file in a folder | `python main.py --upload-dir ./photos` |
| List my cloud files | `python main.py --list-cloud` |
| Download a cloud file | `python main.py --download-cloud <id> --download-dest ./out` |
| Keep existing accounts from expiring | `python main.py -ka` |
| Keep them alive on a schedule | `python main.py -ka --interval 24` |
| Check quota/status of all accounts | `python main.py --health` |
| Export to Bitwarden | `python main.py --export-bitwarden` |
| Resume an interrupted batch | `python main.py -l 20 --resume` |
| See what's using disk space | `python main.py --disk-usage` |
| Watch the browser work | add `-sh` |

---

## Interactive menu

```
MegaTemp v1.8.0
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

**↑ ↓** move · **Enter** select · **Esc** back/exit

Inside **View Credentials**:

| Key | Action |
|---|---|
| `/` | Filter by email, notes, tags, ID or filename |
| `r` | Toggle regex mode (then `/` again) |
| `n` / `t` | Edit notes / tags |
| `a` | Delete every filtered account (type the count to confirm) |
| `p` | Reveal password + strength label |

The menu needs a real terminal. In scripts, Docker, or CI use the CLI flags
instead — MegaTemp will tell you if stdin isn't a TTY.

---

## CLI reference

### Registration

| Flag | Description |
|---|---|
| `-a, --attempts <n>` | Attempts per account (default 4) |
| `-l, --loop <n>` | Create `n` accounts |
| `-j, --parallel <n>` | `n` concurrent workers for `--loop` |
| `--isolate` | Run each worker in its own process (crash isolation, real multicore; more RAM) |
| `--keep-profiles` | Keep per-worker Chromium profiles after the run |
| `--resume` | Resume an interrupted `--loop` batch |
| `--provider <name>` | `mailtm` (default) or `guerrillamail` |
| `--mail-timeout <s>` | Seconds to wait for the confirmation email (default `mailTimeout`, 120) |

### Upload and cloud

| Flag | Description |
|---|---|
| `-f, --file <path>` | Upload a file to the new account |
| `--upload-dir <dir>` | Upload every file in a directory (non-recursive) |
| `-p, --public` | Create a public link for the upload (use with `-f`) |
| `--list-cloud` | List files in the most recent account |
| `--download-cloud <id>` | Download a file by node ID |
| `--download-dest <dir>` | Destination for downloads (default `.`) |

### Export

| Flag | Description |
|---|---|
| `-e, --extract` | Write all credentials to one file |
| `-csv, --export-csv` | Also write `credentials/accounts.csv` |
| `--export-jsonl` | Also write `credentials/accounts.jsonl` |
| `--export-bitwarden` | Bitwarden CSV |
| `--export-onepassword` | 1Password CSV |
| `--export-keepass` | KeePass CSV |

### Proxy

| Flag | Description |
|---|---|
| `--proxy <url>` | Single proxy (`http://user:pass@host:port`) |
| `--proxy-file <path>` | One proxy per line; distributed across workers |
| `--proxy-per-attempt` | Use a fresh proxy on every retry, not just per worker |
| `--proxy-url <url>` | Fetch a proxy list from a URL (plain text or JSON array) |

### Keepalive and health

| Flag | Description |
|---|---|
| `-ka, --keepalive` | Log in to every saved account |
| `--prune` | With `-ka`: delete credentials for accounts that fail login |
| `-y, --yes` | Skip the `--prune` confirmation (required in scripts) |
| `--interval <h>` | With `-ka`: repeat every N hours |
| `--workers <n>` | Max parallel logins for `--health`/`--keepalive` (default 4) |

### Output, security and maintenance

| Flag | Description |
|---|---|
| `-v, --verbose` | Detailed logging |
| `--quiet` | Suppress non-essential output |
| `-sh, --visible` | Show the Chromium window |
| `--json` | JSON output (with `--health`) |
| `--webhook-url <url>` | POST JSON on registration success/failure |
| `--notify` | Desktop notification when a batch finishes |
| `--encryption-password <pw>` | Encrypt stored passwords at rest |
| `--profile <name>` | Use `config-<name>.json` instead of `config.json` |
| `--browser <path>` | Override browser auto-detection |
| `--disk-usage` | Show where disk space is used, then exit |
| `--clean` | Remove stale profiles, `.part` files, update leftovers, old backups |
| `--update` | Check for a newer release (frozen builds only) |
| `--version` | Print the version and exit |

> **Don't** combine `-e`/`-ka` with `-f`/`-p` in one run — do uploads and
> exports as separate invocations.

`--version`, `--health`, exports, `--list-cloud`, `--download-cloud`,
`--keepalive`, `--disk-usage` and `--clean` never launch a browser, so they work
in Docker/cron and on machines without Chromium.

---

## Configuration

`config.json` is created on first run. Edit it by hand or via
**Settings → Edit Config**.

```json
{
  "schemaVersion": 3,
  "executablePath": "",
  "accountFormat": "",
  "proxy": "",
  "proxyFile": "",
  "proxyPerAttempt": false,
  "maxAttempts": 4,
  "csvExport": false,
  "visibleBrowser": false,
  "emailProvider": "mailtm",
  "mailTimeout": 120,
  "quiet": false,
  "encryptionPassword": ""
}
```

| Key | Meaning |
|---|---|
| `executablePath` | Browser binary; empty = auto-detect |
| `accountFormat` | Extra output format, e.g. `"{email}#{password}"` |
| `proxy` / `proxyFile` | Default proxy or proxy list |
| `proxyPerAttempt` | Rotate proxy on every attempt |
| `maxAttempts` | Registration attempts per account |
| `csvExport` | Also write `credentials/accounts.csv` |
| `visibleBrowser` | Same as `-sh` |
| `emailProvider` | Default provider (`mailtm`/`guerrillamail`) |
| `mailTimeout` | Confirmation wait in seconds |
| `quiet` | Same as `--quiet` |
| `encryptionPassword` | Encrypt credentials at rest |

The loader validates paths and values and warns about implausible settings
instead of failing. Unknown keys are kept but ignored. Profiles let you keep
separate configs: `--profile work` reads `config-work.json`.

---

## Credentials

One JSON file per account in `credentials/`:

```json
{
  "email": "user@web-library.net",
  "emailPassword": "inbox-password",
  "password": "mega-password"
}
```

- `email` / `password` — the MEGA login
- `emailPassword` — password for the disposable inbox (needed to read
  confirmation mail later; MegaTemp handles it automatically)

Set `accountFormat` to additionally append accounts to `credentials/accounts.txt`
in any `{email}#{password}`-style layout.

### Encryption

`--encryption-password <pw>` (or `encryptionPassword` in config) encrypts
`password` and `emailPassword` at rest with **AES-256-GCM**. New files use an
`ENC2:` prefix. Files written by older versions (`ENC:` Fernet, `OBS:`
obfuscation) are still readable, so you can upgrade in place.

Lose the password and the secrets are unrecoverable — there is no backdoor.
Exports and the viewer always decrypt in memory; nothing prints `ENC2:` blobs.

---

## Parallelism and reliability (advanced)

**`--parallel N`** (alias `-j`) runs N independent browsers in one process.
Each worker claims the next index from a shared counter, so fast workers do more
accounts instead of waiting. Output is prefixed with `[wN]`, and each finished
worker prints a `[done/total] ok=… failed=…` line.

- **Proxies:** one entry per worker from `--proxy-file`; with
  `--proxy-per-attempt` a new proxy is used for each retry.
- **Hashcash:** MEGA's proof-of-work solver shares a global thread budget, so N
  workers don't spawn 4N hashing threads and starve each other.
- **Email polling:** starts at 1 s, backs off to 3 s with ±20 % jitter.

**`--isolate`** runs each worker in a separate OS process instead. One crashed
Chromium can't stall the batch, and the GIL stops being a factor, at the cost of
higher RAM. Process mode uses temporary Chrome profiles per worker.

**Retries and resume:** `--resume` reads `loop_state.json` and skips accounts
already completed in an interrupted batch. `-a` controls attempts;
`maxAttempts` in config is the default.

**Keepalive:** `-ka` logs in to every saved account. Accounts are marked dead
only on definitive auth failures. `--prune` moves credentials to
`credentials/pruned/` (kept to the newest 100) and requires `-y` in scripts.

**Monitoring:** `--health --json` prints a machine-readable snapshot (status,
quota, last login) suitable for cron or a dashboard.

---

## Disk usage

MegaTemp keeps Chromium profiles, downloads and backups out of the project
directory, so a crash can't bloat the repo:

| Location | What | Cleanup |
|---|---|---|
| `%TEMP%/MegaTemp/` | Per-run Chromium profiles (10–80 MB each) | Swept after 24 h at startup; `--clean` |
| `credentials/` | One JSON file per account | `--prune` or manual |
| `credentials/pruned/` | Backup of pruned accounts | Newest 100 kept; `--clean` |
| `*.part` | Interrupted downloads | `--clean` |
| `<exe>.old` / `<exe>.new` | Auto-update leftovers | Removed on startup; `--clean` |

```bash
python main.py --disk-usage    # per-location breakdown
python main.py --clean         # remove everything reclaimable
python scripts/disk_report.py  # runtime + build artifacts (dev)
```

Chromium's disk and media caches are capped at 1 MB per profile and the shader
cache is disabled. Release binaries are ~11–13 MB and CI fails any build above
25 MB.

---

## Docker

```bash
docker build -t megatem .
docker run -it -v "$PWD/credentials:/app/credentials" megatem
```

Or with Compose (persistent credentials + healthcheck):

```bash
docker compose up
```

The image installs Chromium and points Pyppeteer at it. There is no TTY in a
detached container, so use flags such as `-l 5` or `--health` rather than the
interactive menu.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| "Browser not found" | Pass `--browser /path/to/chrome` or set `executablePath` |
| Registration form never renders / times out | MEGA rate-limits or blocks the IP. Wait, retry, or use a proxy; add `-sh -v` to watch |
| Accounts stop at `-9` | MEGA's hashcash challenge was refused; retry later or from another IP |
| Menu says a terminal is required | stdin isn't a TTY (Docker/cron). Use CLI flags |
| Garbled characters on Windows | `set MEGATEMP_ASCII=1`; `set NO_COLOR=1` disables colour |
| "Failed to decrypt" | Wrong `encryptionPassword`; exports can't recover it |
| Prune deletes too much | Without `-y` it asks first; backups are in `credentials/pruned/` |

More detail: [Troubleshooting](./docs/Troubleshooting.md).

---

## Development

```bash
python -m pytest tests/ -q      # unit + regression tests
python _test_smoke.py           # import/CLI smoke suite
ruff check . && ruff format .   # lint + format (tabs)
python scripts/bench_parallel.py# parallel start-up/claim benchmark
```

Project layout, architecture notes and release steps live in
[Development](./docs/Development.md). See
[`docs/AUDIT-2026-11-11.md`](./docs/AUDIT-2026-11-11.md) for the last full
audit.

---

## Documentation

| Doc | Contents |
|---|---|
| [Installation](./docs/Installation.md) | Venv, browsers, building EXEs |
| [Usage](./docs/Usage.md) | Worked examples |
| [Configuration](./docs/Configuration.md) | Every config key |
| [Troubleshooting](./docs/Troubleshooting.md) | Known issues |
| [Development](./docs/Development.md) | Tests, layout, releases |
| [Changelog](./CHANGELOG.md) | What changed, version by version |

---

## License

**GNU General Public License v3.0** — see [LICENSE](./LICENSE).

Forked from
[qtchaos/py_mega_account_generator](https://github.com/qtchaos/py_mega_account_generator).
