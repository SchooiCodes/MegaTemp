# Development

## Project layout

```
MegaTemp/
├── main.py                 # TUI, argument handling, registration loop + browser reuse
├── config.json             # Browser path + credential format (gitignored)
├── requirements.txt
├── pyproject.toml          # Ruff / mypy config
├── MegaTemp.spec           # PyInstaller spec
├── _test_full_e2e.py       # 52-test comprehensive test suite
├── services/
│   ├── alive.py            # Keepalive service
│   ├── upload.py           # File upload + public link
│   └── extract.py          # Credential export
├── utilities/
│   ├── web.py              # Browser automation (register / confirm / mail)
│   ├── etc.py              # Helpers (credentials, printing, updates, status line)
│   ├── menu.py             # Zero-dependency terminal menu engine
│   ├── fs.py               # Config + credential file I/O
│   └── models.py           # Data types (Colours, Credentials, Config)
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
pytest _test_full_e2e.py -v
```

The test suite covers all modules (52 tests): models, fs, etc, web, menu,
extract, upload, and main. Tests use `tmp_path` isolation and `capsys` for
stdout capture.

A GitHub Actions workflow is planned to run tests on every push.

## How registration works

1. `generate_mail()` creates a mail.tm inbox (unique random address, jittered
   backoff, cached domain list).
2. `type_name()` / `type_password()` fill the MEGA sign-up form using
   `_robust_type()` (focus, prime, clear, type with delay, verify).
3. `finish_form()` submits and `mail_login()` + `get_mail()` fetch the
   confirmation link.
4. `initial_setup()` opens the link, re-enters the password, and waits for the
   account to be created. On failure it raises so the run retries with a fresh
   email.

### Browser lifecycle

- **Single account**: a browser is launched per call to `register()`, closed
  when done.
- **Loop mode**: the browser is launched once and shared across all iterations
  via the `_browser` parameter (saves ~8s per account).

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

## Releasing

Push a version tag to trigger an automated release:

```bash
git tag v1.2.0
git push --tags
```

This runs the build workflow, creates a GitHub Release with auto-generated
notes, and attaches:
- `MegaTemp-linux` (Linux executable)
- `MegaTemp-windows.exe` (Windows executable)
- `MegaTemp-macos` (macOS executable)
- `MegaTemp-{version}-src.tar.gz` (source tarball)

## Contributing

See [CONTRIBUTING.md](https://github.com/SchooiCodes/MegaTemp/blob/master/CONTRIBUTING.md).
Keep commits focused, run Ruff + mypy + tests, and update docs when behaviour
changes.
