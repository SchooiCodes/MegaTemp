# MegaTemp

> Generate MEGA accounts from the command line, upload files, and produce
> shareable links — as many times as you like, with loops.

MegaTemp automates MEGA account registration using a disposable
[mail.tm](https://mail.tm) inbox for confirmation and a headless Chromium
browser for the sign-up flow. It can also upload files to the freshly created
account and hand back a public share link, keep generated accounts "alive" by
periodically logging in, and export credentials in a custom format.

---

## ⚠️ Disclaimer

This project is provided for **educational and personal-automation purposes
only**. Automated account creation may violate [MEGA's Terms of
Service](https://mega.nz/terms). The authors are not responsible for any
misuse, account suspension, or other consequences resulting from the use of
this software. Use it at your own risk and in accordance with the laws and
terms that apply to you.

---

## Acknowledgements

MegaTemp is a fork of
[**qtchaos/py_mega_account_generator**](https://github.com/qtchaos/py_mega_account_generator),
which did the original heavy lifting (the mail.tm integration, the MEGA
browser automation, and the upload/keepalive services). All credit for the
original design and implementation goes to **qtchaos**.

This fork focuses on:

- Making registration actually **succeed** on current MEGA markup (the upstream
  flow silently created dead accounts — see *How it works* below).
- Robustness fixes for modern Python (3.11+), `tenacity` and `pymailtm`
  compatibility, and headless Chromium on Linux.
- A friendly interactive **terminal menu** (arrow-key navigation) for everyday
  use, plus a full **CLI** for scripting.
- Cleaner repository hygiene (license, code of conduct, contributing guide,
  security policy, issue/PR templates).

MegaTemp is distributed under the same **GPL-3.0** license as the upstream
project, in compliance with the GPL.

---

## Features

- 🖥️ **Interactive menu** — run `python main.py` with no arguments to get an
  arrow-key driven TUI: create accounts, loop-create, view/export credentials,
  keep accounts alive, upload files, and tweak settings.
- 🪄 **One-command account generation** — `python main.py` spits out a working
  MEGA account and saves its credentials.
- 📧 **Disposable email** — uses [mail.tm](https://mail.tm) so no real inbox is
  required; confirmation links are fetched automatically.
- 🌐 **Headless browser** — drives MEGA's sign-up SPA with Pyppeteer +
  Chromium (or any Chromium-based browser).
- 👁️ **Visible mode** — pass `-sh` / `--visible` to watch the browser do its
  thing instead of running headless.
- 📤 **File upload + public links** — upload a file to each new account and get
  a shareable link (`-f`, `-p`).
- 🔁 **Loops** — generate or upload as many times as you want (`-l`).
- 💤 **Keepalive** — log into every saved account to keep it from being purged
  (`-ka`).
- 📝 **Custom credential formats** — control exactly how credentials are saved,
  or export every account to `credentials/accounts.csv` (`--export-csv`).
- 🔧 **Configurable attempts** — `-a N` / `--attempts N` caps how many times a
  registration retries with a fresh email before giving up (default 4).
- 📊 **Loop summary** — mass-generation prints success/failure counts, total
  elapsed time, and average per account.

---

## Requirements

| Requirement | Notes |
| --- | --- |
| **Python** | 3.10 or newer (tested on 3.14). |
| **A Chromium-based browser** | Chromium, Chrome, Brave or Edge. The executable path is configured in `config.json`. |
| **Git** | Only needed to clone the repo. |
| **Internet access** | Required for mail.tm and mega.nz. |

> [!NOTE]
> The maximum upload size of a file is **20 GB**, since this is the limit on a
> free MEGA account.

---

## Installation

```bash
git clone https://github.com/SchooiCodes/MegaTemp.git
cd MegaTemp

# Create an isolated environment (recommended)
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

### Configuring the browser

Open `config.json` and point `executablePath` at your Chromium-based browser.
For example, on many Linux systems:

```json
{
  "executablePath": "/usr/bin/chromium",
  "accountFormat": ""
}
```

If `executablePath` is left empty, the program will prompt you for it on first
run.

> [!TIP]
> On Linux you almost always need `--no-sandbox`. MegaTemp already adds the
> required Chromium flags (`--no-sandbox`, `--disable-setuid-sandbox`, …) for
> you, so a plain `executablePath` is enough.

---

## Usage

### Interactive menu (default)

Run it with **no arguments** to open the terminal menu:

```bash
python main.py
```

Use the **↑ / ↓** arrows to move the selection, **Enter** to choose, **Esc** to
go back / exit, and the **← / →** arrows inside the *Settings* submenu to
toggle options.

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

The **Settings** submenu lets you change, for the duration of the session:

| Setting | Effect |
| --- | --- |
| **Max Attempts** | How many times registration retries with a fresh email (default 4). |
| **Visible Browser** | Run Chromium in a visible window instead of headless. |
| **Auto CSV Export** | Also append every new account to `credentials/accounts.csv`. |

### Command-line / scripting

Every menu action is also available as a flag, which is handy in scripts.

```bash
# Create a single account (headless, verbose)
python main.py -v

# Create a visible account so you can watch
python main.py -sh

# Upload a file and get a public share link
python main.py -f FILENAME -p

# Keep every saved account alive
python main.py -ka -v

# Mass-generation summary after 20 attempts, 8 retries each, CSV export
python main.py -l 20 -a 8 --export-csv
```

> [!WARNING]
> Do not combine the **Services** arguments (`-e`, `-ka`) with the file-upload
> arguments (`-f`, `-p`).

---

## Arguments

| Argument | Description |
| --- | --- |
| `-f <file>`, `--file <file>` | Uploads a file to the generated account. |
| `-p`, `--public` | Generates a shareable link to the uploaded file (use with `-f`). |
| `-l <n>`, `--loop <n>` | Loops the program `n` times and prints a summary. |
| `-e`, `--extract` | Compiles all saved `.json` credentials into a single file using the configured format. |
| `-ka`, `--keepalive` | Logs into the accounts to keep them alive. |
| `-v`, `--verbose` | Verbose logging (registration steps, mail addresses, keepalive storage). |
| `-sh`, `--visible` | Run Chromium visibly (non-headless) so you can watch it work. |
| `-a <n>`, `--attempts <n>` | Max registration attempts before giving up (default: 4). |
| `-csv`, `--export-csv` | Also export every saved account to `credentials/accounts.csv`. |

---

## Credential format

By default each account is saved as a separate, human-readable JSON file under
`credentials/`:

```json
{
  "email": "*******@*******.com",
  "emailPassword": "*****",
  "password": "*********"
}
```

- `email` / `password` — use these to log into the **MEGA** account later.
- `emailPassword` — the password of the disposable **mail.tm** inbox (handy if
  you ever need to re-check the inbox).

With `--export-csv`, every account is also appended to
`credentials/accounts.csv` in `email,password,emailPassword` form.

### Custom format

Set `accountFormat` in `config.json` to control the output. The following
placeholders are supported:

| Placeholder | Meaning |
| --- | --- |
| `{email}` | Email used for the MEGA account. |
| `{emailPassword}` | Password of the mail.tm inbox. |
| `{password}` | Password of the MEGA account. |

For example, to write `email#password` lines to `credentials/accounts.txt`,
set:

```json
{ "accountFormat": "{email}#{password}" }
```

Setting `accountFormat` to `""` restores the default per-account JSON files.

---

## How it works (and why this fork exists)

The registration flow has two browser phases:

1. **Sign-up** — Pyppeteer fills the MEGA registration form
   (`#register-firstname`, `#register-email`, `#register-password`) and submits
   it. MEGA's password field uses a custom input handler, so the value must be
   typed with an explicit focus + per-character delay or it ends up **empty**.
2. **Confirmation** — the confirmation link from mail.tm opens a page where the
   account password is entered a second time to finish creating the account.

The upstream project typed the registration password with `page.type()` right
after focusing the field. MEGA's custom password input drops the **first
keystroke** when typing starts immediately after focus, so the stored password
was silently one character short of what we typed. Confirmation then rejected
it (`Invalid password`) and the saved credentials were **dead** — logging in
later reported *"invalid email or password."*

MegaTemp fixes this by:

- Typing the password through a robust routine in `utilities/web.py`
  (`_robust_type`): focus, prime with a throwaway character, clear it, then type
  the real password with a per-character delay, and **verify** the field holds
  the exact value before continuing (it raises otherwise, so a dead account is
  never saved).
- Typing the email through the same robust routine so the first character is
  never dropped.
- Detecting a *successful* confirmation by leaving the confirm page (the
  recovery-key screen) instead of relying on an outdated `#freeStart` selector,
  and raising on failure so the run retries with a fresh email.
- Creating a fresh browser page per attempt so a transient Pyppeteer error
  can't poison the retry loop.
- Capping the mail-tm polling and account-generation retries so the program
  can never hang forever.

---

## Project layout

```
MegaTemp/
├── main.py              # Entry point: TUI, argument handling, registration loop
├── config.json          # Browser path + credential format (gitignored)
├── requirements.txt
├── pyproject.toml       # Ruff / mypy config
├── services/
│   ├── alive.py         # Keepalive service
│   ├── upload.py        # File upload + public link
│   └── extract.py       # Credential export
├── utilities/
│   ├── web.py           # Browser automation (register / confirm / mail)
│   ├── etc.py           # Helpers (credentials, printing, updates, status line)
│   ├── menu.py          # Zero-dependency interactive terminal menu engine
│   ├── fs.py            # Config + credential file I/O
│   └── types.py         # Data types (Colours, Credentials, Config)
└── .github/             # CI + community health files
```

---

## Development

Formatting/linting is handled by [Ruff](https://docs.astral.sh/ruff/) (configured
in `pyproject.toml`). A GitHub Actions workflow runs it on every push/PR.

```bash
pip install ruff
ruff check .
ruff format .
```

Contributions are welcome — see [CONTRIBUTING.md](./CONTRIBUTING.md).

---

## Documentation

- The [docs/](./docs/) folder holds the full guide: installation, usage,
  configuration, troubleshooting, and development.
- A [CHANGELOG.md](./CHANGELOG.md) tracks every release.

---

## License

Distributed under the **GNU General Public License v3.0**. See
[LICENSE](./LICENSE).

This program is free software: you can redistribute it and/or modify it under
the terms of the GPLv3. It is provided without warranty of any kind.

---

<p align="center">
  Forked from <a href="https://github.com/qtchaos/py_mega_account_generator">qtchaos/py_mega_account_generator</a>
  · Licensed under GPL-3.0
</p>
