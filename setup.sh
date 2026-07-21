#!/usr/bin/env bash
set -euo pipefail

# MegaTemp — setup script
# Installs system dependencies, creates a venv, installs Python packages,
# and generates a default config.

PYTHON="${PYTHON:-python3}"
VENV_DIR="${VENV_DIR:-venv}"

echo "==> Checking Python..."
if ! command -v "$PYTHON" &>/dev/null; then
	echo "ERROR: $PYTHON not found. Install Python 3.10+ first."
	exit 1
fi

echo "==> Creating virtualenv ($VENV_DIR)..."
"$PYTHON" -m venv "$VENV_DIR"

echo "==> Installing requirements..."
"$VENV_DIR/bin/pip" install --upgrade pip setuptools wheel
"$VENV_DIR/bin/pip" install -r requirements.txt

echo "==> Creating credentials directory..."
mkdir -p credentials

echo "==> Generating default config..."
if [ ! -f config.json ]; then
	cat > config.json <<'CONFIG'
{
	"schemaVersion": 1,
	"executablePath": "",
	"accountFormat": "",
	"proxy": "",
	"proxyFile": "",
	"proxyPerAttempt": false,
	"maxAttempts": 4,
	"csvExport": false,
	"visibleBrowser": false,
	"emailProvider": "mailtm"
}
CONFIG
	echo "config.json created."
else
	echo "config.json already exists — skipping."
fi

echo ""
echo "Setup complete! Activate with:  source $VENV_DIR/bin/activate"
echo "Then run:  python main.py"
