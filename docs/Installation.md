# Installation

## Quick start

```bash
git clone https://github.com/SchooiCodes/MegaTemp.git
cd MegaTemp
python -m venv venv
source venv/bin/activate            # Windows: venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## Requirements

| Requirement | Notes |
| --- | --- |
| Python | 3.10 or newer (tested on 3.14) |
| Chromium-based browser | Chromium, Chrome, Brave, or Edge |
| Internet | mail.tm and mega.nz must be reachable |

## Configure the browser

On first run, MegaTemp searches common install paths for a Chromium-based
browser. If none is found, you're prompted to enter the path manually.

You can also set it in `config.json` ahead of time:

```json
{
  "executablePath": "/usr/bin/chromium",
  "accountFormat": ""
}
```

Required Chromium flags (`--no-sandbox`, `--disable-gpu`, etc.) are added
automatically — you only need the executable path.

## Verify

```bash
python main.py -v
```

You should see the registration flow run end-to-end and credentials saved to
the `credentials/` folder.

---

## Standalone executable (no Python)

Prebuilt binaries for **Linux, Windows, and macOS** are attached to every
[GitHub Release](https://github.com/SchooiCodes/MegaTemp/releases). No Python
installation needed — download the right binary for your OS and run it.

> [!IMPORTANT]
> The binary contains Python + all libraries, but **not** Chromium. The target
> machine still needs a Chromium-based browser installed.

### Build it yourself

```bash
pip install -r requirements.txt pyinstaller
pyinstaller MegaTemp.spec --noconfirm --clean
# -> dist/MegaTemp  (Windows: dist/MegaTemp.exe)
```
