# Contributing to MegaTemp

Thanks for your interest in improving MegaTemp! This document explains how to
get set up and what we look for in contributions.

## Getting started

1. **Fork** the repository and clone your fork.
2. Create a Python virtual environment and install dependencies:

   ```bash
   python -m venv venv
   source venv/bin/activate        # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. Point `config.json`'s `executablePath` at a Chromium-based browser.
4. Run `python main.py` to confirm everything works locally.

## Making changes

- Create a feature branch off `master`: `git checkout -b my-change`.
- Keep commits focused and write clear messages.
- Format and lint with [Ruff](https://docs.astral.sh/ruff/) before pushing:

  ```bash
  ruff check .
  ruff format .
  ```

  (A GitHub Actions workflow also runs Ruff on every push/PR.)
- Update `README.md` and the relevant docs when behavior changes.

## Reporting bugs & requesting features

- Search [existing issues](https://github.com/SchooiCodes/MegaTemp/issues)
  before opening a new one.
- Use the provided issue templates where possible.
- Include your OS, Python version, browser, and the full error output.

## Pull requests

- Open PRs against `master`.
- Describe **what** changed and **why**, and reference any related issues.
- Make sure CI is green.
- By contributing, you agree that your contributions are licensed under the
  project's [GPL-3.0](./LICENSE) license.

## Code of Conduct

By participating, you agree to abide by our
[Code of Conduct](./CODE_OF_CONDUCT.md).
