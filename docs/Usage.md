# Usage

## Interactive menu (default)

Run `main.py` with no arguments to open the terminal menu. Navigate with
**↑ / ↓**, choose with **Enter**, go back / exit with **Esc**, and toggle
settings with **← / →** inside the *Settings* submenu.

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

### Menu options

| Option | What it does |
|--------|-------------|
| **Create Account** | Registers one account and saves credentials |
| **Loop Create** | Prompts for a count and registers that many accounts (shares one browser) |
| **View Credentials** | Lists every saved account with masked passwords and file sizes |
| **Export Credentials** | Writes all accounts to `credentials.txt` (warns if file exists) |
| **Keep Alive Accounts** | Logs into every saved account to prevent MEGA from purging them |
| **Upload File** | Prompts for a file path (`~` is expanded) and uploads to the latest account |
| **Settings** | Max attempts, visible browser, auto CSV export |
| **Exit** | Asks for confirmation before quitting |

The **Settings** submenu controls, for the session:

- **Max Attempts** — registration retries with a fresh email (default 4).
- **Visible Browser** — run Chromium visibly instead of headless.
- **Auto CSV Export** — also append each account to `credentials/accounts.csv`.

#### Upload behaviour

If the file path you enter doesn't exist, MegaTemp shows "File not found" and
asks if you'd like to try a different path — no need to restart.

#### Export behaviour

If `credentials.txt` already exists, MegaTemp asks for confirmation before
overwriting it.

---

## Command-line reference

| Argument | Description |
| --- | --- |
| `-f <file>`, `--file <file>` | Upload a file to the generated account. |
| `-p`, `--public` | Public share link for the uploaded file (use with `-f`). |
| `-l <n>`, `--loop <n>` | Loop `n` times; prints a summary. |
| `-e`, `--extract` | Compile all saved credentials into one file. |
| `-ka`, `--keepalive` | Log into accounts to keep them alive. |
| `-v`, `--verbose` | Verbose logging. |
| `-sh`, `--visible` | Run Chromium visibly. |
| `-a <n>`, `--attempts <n>` | Max registration attempts (default 4). |
| `-csv`, `--export-csv` | Also export to `credentials/accounts.csv`. |

## Examples

```bash
python main.py -v                       # one account, verbose
python main.py -sh                      # watch the browser
python main.py -f song.mp3 -p           # upload + public link
python main.py -ka -v                   # keep accounts alive (verbose shows storage)
python main.py -l 20 -a 8 --export-csv  # mass-generate with summary
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
