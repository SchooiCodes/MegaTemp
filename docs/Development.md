# Development

## Project layout

```
MegaTemp/
├── main.py                 # TUI, argument handling, registration loop + browser reuse
├── config.json             # Browser path + credential format (gitignored)
├── requirements.txt
├── pyproject.toml          # Ruff / mypy config
├── MegaTemp.spec           # PyInstaller spec
├── Dockerfile              # Container build
├── docker-compose.yml      # Docker Compose with persistent volumes
├── tests/                   # 163-test per-module test suite
├── services/
│   ├── alive.py            # Keepalive service
│   ├── upload.py           # File upload + public link + progress bar
│   ├── download.py         # Cloud file listing + download
│   └── extract.py          # Credential export
├── utilities/
│   ├── web.py              # Browser automation (register / confirm / mail)
│   ├── etc.py              # Helpers (colours, notify, ProxyManager, VERSION)
│   ├── menu.py             # Zero-dependency terminal menu engine + path completion
│   ├── fs.py               # Config + credential file I/O + config validation
│   ├── models.py           # Data types (Credentials with notes/tags, Config)
│   ├── provider.py         # EmailProvider ABC + registry
│   ├── mailtm_provider.py  # mail.tm EmailProvider implementation
│   ├── guerrilla.py        # Guerrilla Mail EmailProvider implementation
│   ├── retry.py            # @retry decorator (tenacity / pure-Python fallback)
│   └── password_strength.py# Entropy-based password strength estimation
├── docs/                   # Documentation
└── .github/                # CI + community health files
    └── workflows/
        ├── ruff.yml        # Ruff lint + format check
        ├── build.yml       # PyInstaller build + release upload
        └── release.yml     # Source tarball upload to releases
```

## Lint & format

```bash
pip install ruff
ruff check .
ruff format .
```

A GitHub Actions workflow runs both checks on every push and pull request.

## Type checking

```bash
pip install mypy
mypy .
```

All source files pass strict mypy checks.

## Tests

```bash
pip install pytest pytest-asyncio
pytest tests/ -v
```

The test suite covers all modules (97 tests): models, fs, etc, menu,
extract, upload, download, retry, password_strength, provider, notify, and CLI
dispatch. Tests use `tmp_path` isolation, `capsys` for stdout capture, and
`monkeypatch` for input mocking.

A GitHub Actions workflow runs tests on every push.

## How registration works

1. `generate_mail()` creates a disposable inbox (mail.tm or Guerrilla Mail,
   selected via `--provider` or `config.emailProvider`).
2. `type_name()` / `type_password()` fill the MEGA sign-up form using
   `_robust_type()` (focus, prime, clear, type with delay, verify).
3. `finish_form()` submits and `mail_login()` + `get_mail()` fetch the
   confirmation link.
4. `initial_setup()` opens the link, re-enters the password, and waits for the
   account to be created. On failure it raises so the run retries with a fresh
   email.

### Provider system

Email providers implement the `EmailProvider` ABC in `utilities/provider.py`:

- **MailTmProvider** (`utilities/mailtm_provider.py`) — wraps the
  `pymailtm` library for mail.tm inboxes.
- **GuerrillaMailProvider** (`utilities/guerrilla.py`) — uses the Guerrilla
  Mail REST API directly (no signup, no API key).

Providers auto-register on import via `register_provider()` at the bottom of
`utilities/provider.py`. New providers need only an `EmailProvider` subclass
and a `register_provider(name, cls)` call.

### Browser lifecycle

- **Single account**: a browser is launched per call to `register()`, closed
  when done.
- **Loop mode**: the browser is launched once and shared across all iterations
  via the `_browser` parameter (saves ~8s per account).
- **Parallel mode**: each worker launches its own browser.

## Building the executable

A standalone binary (no Python on the target machine) is built with PyInstaller:

```bash
pip install pyinstaller
pyinstaller MegaTemp.spec --noconfirm --clean
```

> [!NOTE]
> The built binary contains Python + all libraries, but **not** Chromium. The
> target machine still needs a Chromium-based browser installed.

The CI workflow `.github/workflows/build.yml` builds Linux/Windows/macOS
artifacts automatically on every push and attaches them to GitHub Releases when
a tag is pushed (`v*`).

## Encryption

`--encryption-password` / `config["encryptionPassword"]` encrypts saved passwords
at rest using Fernet (from the `cryptography` package). If `cryptography` is not
installed, a best-effort base64+XOR obfuscation is used instead with a warning.
Credentials with encrypted fields carry the `ENC:` prefix (Fernet) or `OBS:`
prefix (obfuscation) in the password/emailPassword fields. Decryption is
automatic in `list_credentials()` and triggered by `decrypt_credential()`.

## Custom Exceptions

`utilities/exceptions/` defines a typed hierarchy: `MegaTempError` (base) →
`RegistrationError`, `ConfigError`, `CredentialError`, `ProxyError`,
`EmailProviderError`, `BrowserError`, `APIError`, `AccountError`. New code
should raise and catch these instead of bare `Exception` where practical.

## Webhooks

`send_webhook(url, event, data)` POSTs a JSON payload `{"event": ..., "data": ...}`
to the configured URL. Fired on `registration_success` and `registration_failed`.
Best-effort with 10s timeout — errors are silently swallowed.

## Config Profiles

`--profile NAME` delegates to `set_config_profile()` in `fs.py`, which changes
`_config_path()` from `config.json` to `config-{NAME}.json`. Each profile is a
fully independent config file.

## Releasing

Push a version tag to trigger an automated release:

```bash
git tag v1.4.0
git push --tags
```

This runs the build workflow, creates a GitHub Release with auto-generated
notes, and attaches:
- `MegaTemp-linux` (Linux executable)
- `MegaTemp-windows.exe` (Windows executable)
- `MegaTemp-macos` (macOS executable)
- `MegaTemp-{version}-src.tar.gz` (source tarball)

To update an existing tag to the current HEAD:

```bash
	git tag -f v1.4.0 HEAD
	git push origin v1.4.0 --force
```

> [!WARNING]
> Force-pushing a tag triggers the release workflow again, which builds new
> binaries and creates a new release with the same tag.

## Contributing

See [CONTRIBUTING.md](https://github.com/SchooiCodes/MegaTemp/blob/master/CONTRIBUTING.md).
Keep commits focused, run Ruff + mypy + tests, and update docs when behaviour
changes.
