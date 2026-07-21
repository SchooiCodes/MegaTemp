# MegaTemp Documentation

**MegaTemp** automates MEGA.nz account registration using a disposable
[mail.tm](https://mail.tm) inbox for confirmation and a headless Chromium
browser for the sign-up flow. Upload files, keep accounts alive, export
credentials — all from an interactive terminal menu or CLI flags.

> ⚠️ For educational and personal-automation purposes only. Automated account
> creation may violate MEGA's Terms of Service. Use at your own risk.

---

## Quick start

```bash
git clone https://github.com/SchooiCodes/MegaTemp.git
cd MegaTemp
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python main.py
```

See [Installation](Installation) for details (browser config, standalone
executable).

---

## Pages

| Page | What it covers |
|------|----------------|
| [Installation](Installation) | Clone, venv, dependencies, browser config, PyInstaller build |
| [Usage](Usage) | Interactive TUI reference, CLI flags, examples |
| [Configuration](Configuration) | `config.json`, `accountFormat`, session settings |
| [Troubleshooting](Troubleshooting) | Dead accounts, blank pages, missing emails, Chromium launch failures |
| [Development](Development) | Project layout, linting, test suite, how registration works |

---

## Key features

- **Single account** — run `python main.py` for the interactive menu
- **Mass generation** — menu → *Loop Create* or `python main.py -l 10`
- **File upload** — `python main.py -f photo.jpg -p` (includes public link)
- **Keep alive** — `python main.py -ka` logs into every saved account
- **Export** — menu → *Export Credentials* or `python main.py -e`
- **Disposable email** — mail.tm inboxes, no real email required
- **Headless browser** — Pyppeteer + Chromium (visible mode with `-sh`)
- **Prebuilt binaries** — [Releases](https://github.com/SchooiCodes/MegaTemp/releases)

---

## Getting help

1. Check [Troubleshooting](Troubleshooting) for common issues.
2. Search [existing GitHub Issues](https://github.com/SchooiCodes/MegaTemp/issues).
3. Open a [new issue](https://github.com/SchooiCodes/MegaTemp/issues/new) with
   the output of `python main.py -v` and a description of the problem.
