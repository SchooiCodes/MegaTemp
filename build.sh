#!/usr/bin/env bash
# Build a standalone MegaTemp executable with PyInstaller.
# The result is a single file in dist/ that runs on machines WITHOUT Python,
# as long as a Chromium-based browser is installed (Chromium is NOT bundled).
set -e

PY="${PY:-python3}"
if [ ! -x "$PY" ]; then
	PY="$(command -v python3 || command -v python)"
fi

echo ">> Installing PyInstaller (if needed)..."
"$PY" -m pip install -r requirements.txt
"$PY" -m pip install pyinstaller

echo ">> Building MegaTemp (this may take a minute)..."
"$PY" -m PyInstaller MegaTemp.spec --noconfirm --clean

echo
echo "Done. Executable is at: dist/MegaTemp"
echo "NOTE: the target machine still needs a Chromium-based browser installed."
echo "      Set its path in config.json (executablePath) on first run."
