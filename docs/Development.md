# Development

## Project layout

```
MegaTemp/
├── main.py              # TUI, argument handling, registration loop
├── config.json          # Browser path + credential format (gitignored)
├── services/
│   ├── alive.py         # Keepalive service
│   ├── upload.py        # File upload + public link
│   └── extract.py       # Credential export
├── utilities/
│   ├── web.py           # Browser automation (register / confirm / mail)
│   ├── etc.py           # Helpers (credentials, printing, updates, status line)
│   ├── menu.py          # Zero-dependency terminal menu engine
│   ├── fs.py            # Config + credential file I/O
│   └── types.py         # Data types (Colours, Credentials, Config)
└── .github/             # CI + community health files
```

## Lint & format

```bash
pip install ruff
ruff check .
ruff format .
```

A GitHub Actions workflow runs `ruff check` and `ruff format --check` on every
push and pull request (across Python 3.10–3.14).

## How registration works

1. `generate_mail()` creates a mail.tm inbox (bounded retries).
2. `type_name()` / `type_password()` fill the MEGA sign-up form using
   `_robust_type()` (focus, prime, clear, type with delay, verify).
3. `finish_form()` submits and `mail_login()` + `get_mail()` fetch the
   confirmation link.
4. `initial_setup()` opens the link, re-enters the password, and waits for the
   account to be created. On failure it raises so the run retries with a fresh
   email.

## Contributing

See [CONTRIBUTING.md](https://github.com/SchooiCodes/MegaTemp/blob/master/CONTRIBUTING.md).
Keep commits focused, run Ruff, and update docs when behavior changes.
