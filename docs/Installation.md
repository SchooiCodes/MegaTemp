# Installation

## 1. Clone

```bash
git clone https://github.com/SchooiCodes/MegaTemp.git
cd MegaTemp
```

## 2. Virtual environment

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## 3. Configure the browser

Open `config.json` and set `executablePath` to your Chromium-based browser:

```json
{
  "executablePath": "/usr/bin/chromium",
  "accountFormat": ""
}
```

If left empty, MegaTemp prompts for it on first run. Required Chromium flags
(`--no-sandbox`, `--disable-setuid-sandbox`, …) are added automatically, so you
normally only need the executable path.

## 4. Verify

```bash
python main.py -v
```

You should see the registration flow run end-to-end and an account saved to
`credentials/`.

## Requirements

| Requirement | Notes |
| --- | --- |
| Python | 3.10+ (tested on 3.14) |
| Chromium-based browser | Chromium, Chrome, Brave, or Edge |
| Internet | mail.tm and mega.nz must be reachable |
