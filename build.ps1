# Build a standalone MegaTemp executable with PyInstaller (Windows).
# Produces a single file in dist\ that runs on machines WITHOUT Python,
# as long as a Chromium-based browser is installed (Chromium is NOT bundled).
$ErrorActionPreference = "Stop"

$py = "python"
Write-Host ">> Installing PyInstaller (if needed)..."
& $py -m pip install -r requirements.txt
& $py -m pip install pyinstaller

Write-Host ">> Building MegaTemp (this may take a minute)..."
& $py -m PyInstaller MegaTemp.spec --noconfirm --clean

Write-Host ""
Write-Host "Done. Executable is at: dist\MegaTemp.exe"
Write-Host "NOTE: the target machine still needs a Chromium-based browser installed."
Write-Host "      Set its path in config.json (executablePath) on first run."
