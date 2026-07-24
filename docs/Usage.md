# Usage

## Interactive menu (default)

Run `main.py` with no arguments to open the terminal menu. Navigate with
**↑ / ↓**, choose with **Enter**, go back / exit with **Esc**, and toggle
settings with **← / →** inside the *Settings* submenu.

```
MegaTemp v1.4.0
╔══════════════════════════════════════════════════════╗
║  Create Account                                      ║
║  Loop Create                                         ║
║  View Credentials                                    ║
║  Export Credentials                                  ║
║  Keep Alive Accounts                                 ║
║  Storage Info                                        ║
║  Upload File                                         ║
║  Upload Directory                                    ║
║  Browse Cloud                                        ║
║  Account Management                                  ║
║  Export as Bitwarden CSV                             ║
║  Export as 1Password CSV                             ║
║  Export as KeePass CSV                               ║
║  Settings                                            ║
║  Exit                                                ║
╚══════════════════════════════════════════════════════╝
```

### Menu options

| Option | What it does |
|--------|-------------|
| **Create Account** | Registers one account and saves credentials |
| **Loop Create** | Prompts for a count and registers that many accounts (shares one browser) |
| **View Credentials** | Lists every saved account with masked passwords, notes, tags, search |
| **Export Credentials** | Writes all accounts to `credentials.txt` (warns if file exists) |
| **Keep Alive Accounts** | Logs into every saved account to prevent MEGA from purging them |
| **Storage Info** | Health dashboard — quota, age, login timestamps per account |
| **Upload File** | Prompts for a file path and uploads to a chosen account |
| **Upload Directory** | Uploads all files in a folder (non-recursive) to a chosen account |
| **Browse Cloud** | Lists cloud files and downloads them interactively |
| **Account Management** | Delete account, change password, create folder |
| **Export as Bitwarden CSV** | Export credentials in Bitwarden-compatible CSV format |
| **Export as 1Password CSV** | Export credentials in 1Password-compatible CSV format |
| **Export as KeePass CSV** | Export credentials in KeePass-compatible CSV format |
| **Settings** | Max attempts, visible browser, CSV/JSONL export, password generator |
| **Exit** | Asks for confirmation before quitting |

The **Settings** submenu controls, for the session:

- **Max Attempts** — registration retries with a fresh email (default 4).
- **Visible Browser** — run Chromium visibly instead of headless.
- **Auto CSV Export** — also append each account to `credentials/accounts.csv`.
- **Auto JSONL Export** — also append each account to `credentials/accounts.jsonl`.
- **Generate Password** — create a cryptographically random password.

#### Upload behaviour

If the file path you enter doesn't exist, MegaTemp shows "File not found" and
asks if you'd like to try a different path — no need to restart.

#### Export behaviour

If `credentials.txt` already exists, MegaTemp asks for confirmation before
overwriting it.

---

## CLI reference

| Flag | Long | Description |
|------|------|-------------|
| `-ka` | `--keepalive` | Log into all saved accounts to keep them alive |
| | `--prune` | With `--keepalive`, delete dead account files |
| | `--interval HOURS` | With `--keepalive`, loop every N hours |
| `-e` | `--extract` | Export all saved credentials to `credentials.txt` |
| `-v` | `--verbose` | Verbose logging of registration steps |
| `-f PATH` | `--file PATH` | Upload a file |
| | `--upload-dir DIR` | Upload all files in a directory (non-recursive) |
| `-p` | `--public` | Generate a public share link (use with `-f`) |
| `-l N` | `--loop N` | Generate N accounts in sequence |
| `-j N` | `--parallel N` | Generate N accounts concurrently (use with `-l`) |
| `-sh` | `--visible` | Show the Chromium window |
| `-a N` | `--attempts N` | Max retries per account (default 4) |
| `-csv` | `--export-csv` | Also save to `credentials/accounts.csv` |
| | `--export-jsonl` | Also save to `credentials/accounts.jsonl` |
| | `--proxy URL` | Single proxy (e.g. `http://user:pass@host:port`) |
| | `--proxy-file PATH` | File with one proxy per line |
| | `--proxy-per-attempt` | Rotate proxy on every registration attempt |
| | `--resume` | Resume an interrupted `--loop` batch |
| | `--list-cloud` | List files in the most recent MEGA account |
| | `--download-cloud ID` | Download a cloud file by its node ID |
| | `--download-dest DIR` | Destination for `--download-cloud` (default `.`) |
| | `--version` | Show version (`MegaTemp v1.4.0`) and exit |
| | `--provider NAME` | Email provider: `mailtm` (default) or `guerrillamail` |
| | `--health` | Show health dashboard for all saved accounts |
| | `--json` | JSON output for `--health` |
| | `--quiet` | Suppress non-essential output for scripting |
| | `--mail-timeout SECS` | Seconds to wait for confirmation email (default 120) |
| | `--webhook-url URL` | POST JSON payload on registration success/failure |
| | `--proxy-url URL` | Auto-fetch proxy list from a remote URL |
| | `--encryption-password PW` | Encrypt saved passwords at rest |
| | `--profile NAME` | Use `config-{NAME}.json` instead of `config.json` |
| | `--export-bitwarden` | Export credentials in Bitwarden CSV format |
| | `--export-onepassword` | Export credentials in 1Password CSV format |
| | `--export-keepass` | Export credentials in KeePass CSV format |

## Examples

```bash
python main.py -v                       # one account, verbose
python main.py -sh                      # watch the browser
python main.py -f song.mp3 -p           # upload + public link
python main.py -ka -v --prune           # keep alive, auto-remove dead accounts
python main.py -l 20 -a 8 --export-csv  # mass-generate with summary
python main.py -l 50 -j 5               # parallel batch (5 concurrent workers)
python main.py -l 50 -j 10 --proxy-file proxies.txt  # parallel + proxy rotation
python main.py -l 20 --resume           # resume interrupted batch
python main.py --list-cloud             # list cloud files
python main.py --download-cloud FILE_ID --download-dest ./downloads  # download
python main.py -ka --interval 24        # keep alive every 24 hours
python main.py --provider guerrillamail # use Guerrilla Mail provider
python main.py --version                # show version
python main.py --health                 # health dashboard from CLI
python main.py --health --json          # health dashboard as JSON
python main.py --quiet                  # suppress output for scripting
python main.py --webhook-url https://hooks.example.com/megatem  # webhook on success
python main.py --proxy-url https://raw.githubusercontent.com/.../proxies.txt  # auto-fetch
python main.py --encryption-password mysecretkey  # encrypt stored passwords
python main.py --profile work           # use config-work.json
python main.py --export-bitwarden       # export Bitwarden CSV from CLI
```

> [!WARNING]
> Do not combine the services flags (`-e`, `-ka`) with the upload flags
> (`-f`, `-p`).

## Loop mode summary

After a batch, MegaTemp prints:

```
─────────────────────── Loop summary ───────────────────────
Total accounts: 5
  Successful:   5
  Failed:       0
  Total time:   2m 22.9s
  Avg / success: 28.6s
```

- **Successful** — accounts that were registered and confirmed.
- **Failed** — accounts that exhausted all registration attempts.
- **Avg / success** — helpful for estimating larger batches.

---

## Standalone executable (no Python required)

Prebuilt binaries for Linux / Windows / macOS are attached to every
[GitHub Release](https://github.com/SchooiCodes/MegaTemp/releases).
No Python installation needed — just download and run.

To build yourself:

```bash
pip install -r requirements.txt pyinstaller
pyinstaller MegaTemp.spec --noconfirm --clean
# -> dist/MegaTemp  (Windows: dist/MegaTemp.exe)
```

Chromium is **not** bundled — the target machine still needs a Chromium-based
browser installed; set its path in `config.json` on first run.
