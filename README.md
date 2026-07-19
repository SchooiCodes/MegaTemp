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
- Cleaner repository hygiene (license, code of conduct, contributing guide).

MegaTemp is distributed under the same **GPL-3.0** license as the upstream
project, in compliance with the GPL.

---

## Features

- 🪄 **One-command account generation** — `python main.py` spits out a working
  MEGA account and saves its credentials.
- 📧 **Disposable email** — uses [mail.tm](https://mail.tm) so no real inbox is
  required; confirmation links are fetched automatically.
- 🌐 **Headless browser** — drives MEGA's sign-up SPA with Pyppeteer +
  Chromium (or any Chromium-based browser).
- 📤 **File upload + public links** — upload a file to each new account and get
  a shareable link (`-f`, `-p`).
- 🔁 **Loops** — generate or upload as many times as you want (`-l`).
- 💤 **Keepalive** — log into every saved account to keep it from being purged
  (`-ka`).
- 📝 **Custom credential formats** — control exactly how credentials are saved.

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

---

## Usage

Run it with no arguments to generate a single account:

```bash
python main.py
```

The credentials are printed to the console and written to the `credentials/`
folder.

### Uploading a file

```bash
python main.py -f FILENAME -p
```

This uploads `FILENAME` to a new account and prints a **publicly shareable
link**.

### Keeping accounts alive

MEGA tends to purge accounts that are never logged into, so run the keepalive
service periodically:

```bash
python main.py -ka -v
```

This logs into every saved account and prints the storage used (`-v` for
verbose).

### Mass generation / uploads

```bash
python main.py -p -f FILENAME -l TIMES_TO_LOOP
```

---

## Credential format

By default each account is saved as a separate JSON file:

```json
{"email": "*******@*******.com", "emailPassword": "*****", "password": "*********"}
```

- `email` / `password` — use these to log into the **MEGA** account later.
- `emailPassword` — the password of the disposable **mail.tm** inbox (handy if
  you ever need to re-check the inbox).

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

## Arguments

> [!WARNING]
> Do not combine the **Services** arguments (`-e`, `-ka`) with the file-upload
> arguments (`-f`, `-p`).

| Argument | Description |
| --- | --- |
| `-f <file>`, `--file <file>` | Uploads a file to the generated account. |
| `-p`, `--public` | Generates a shareable link to the uploaded file (use with `-f`). |
| `-l <n>`, `--loop <n>` | Loops the program `n` times. |
| `-e`, `--extract` | Compiles all saved `.json` credentials into a single file using the configured format. |
| `-ka`, `--keepalive` | Logs into the accounts to keep them alive. |
| `-v`, `--verbose` | Shows storage left while using keepalive. |

---

## How it works (and why this fork exists)

The registration flow has two browser phases:

1. **Sign-up** — Pyppeteer fills the MEGA registration form
   (`#register-firstname`, `#register-email`, `#register-password`) and submits
   it. MEGA's password field uses a custom input handler, so the value must be
   typed with an explicit focus + per-character delay or it ends up **empty**.
2. **Confirmation** — the confirmation link from mail.tm opens a page where the
   account password is entered a second time to finish creating the account.

The upstream project typed the registration password without focus/delay, so
the value was silently dropped. The account was "created" but with no password,
so confirmation rejected it (`Invalid password`) and the saved credentials were
**dead** — logging in later reported *"invalid email or password."*

MegaTemp fixes this by:

- Focusing + typing the password with a small delay in `utilities/web.py`
  (`type_password`), verified to register the real value.
- Detecting a *successful* confirmation by leaving the confirm page (the
  recovery-key screen) instead of relying on an outdated `#freeStart` selector,
  and raising on failure so the run retries with a fresh email rather than
  saving dead credentials.
- Creating a fresh browser page per attempt so a transient Pyppeteer error
  can't poison the retry loop.

---

## Project layout

```
MegaTemp/
├── main.py              # Entry point, argument handling, registration loop
├── config.json          # Browser path + credential format (gitignored)
├── requirements.txt
├── pyproject.toml       # Ruff / mypy config
├── services/
│   ├── alive.py         # Keepalive service
│   ├── upload.py        # File upload + public link
│   └── extract.py       # Credential export
├── utilities/
│   ├── web.py           # Browser automation (register / confirm / mail)
│   ├── etc.py           # Helpers (credentials, printing, etc.)
│   ├── fs.py            # Config + credential file I/O
│   └── types.py         # Data types
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
