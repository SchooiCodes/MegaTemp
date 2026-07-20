# Usage

## Interactive menu (default)

Run `main.py` with no arguments to open the terminal menu. Navigate with
**↑ / ↓**, choose with **Enter**, go back / exit with **Esc**, and toggle
settings with **← / →** inside the *Settings* submenu.

```
MegaTemp v1.1.0
┌────────────────────────────────────────┐
│ > Create Account                       │
│   Loop Create                          │
│   View Credentials                     │
│   Export Credentials                   │
│   Keep Alive Accounts                  │
│   Upload File                          │
│   Settings                             │
│   Exit                                 │
└────────────────────────────────────────┘
```

The **Settings** submenu controls, for the session:

- **Max Attempts** — registration retries with a fresh email (default 4).
- **Visible Browser** — run Chromium visibly instead of headless.
- **Auto CSV Export** — also append each account to `credentials/accounts.csv`.

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
python main.py -ka -v                   # keep accounts alive
python main.py -l 20 -a 8 --export-csv  # mass-generate with summary
```

> [!WARNING]
> Do not combine the services flags (`-e`, `-ka`) with the upload flags
> (`-f`, `-p`).
