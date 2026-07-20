# Home

**MegaTemp** automates MEGA account registration using a disposable
[mail.tm](https://mail.tm) inbox for confirmation and a headless Chromium
browser for the sign-up flow. It can also upload files to the fresh account and
produce a public share link, keep generated accounts "alive" by periodically
logging in, and export credentials in a custom format.

This project is provided for **educational and personal-automation purposes
only**. Automated account creation may violate MEGA's Terms of Service. Use it
at your own risk.

## Quick start

```bash
git clone https://github.com/SchooiCodes/MegaTemp.git
cd MegaTemp
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
# point config.json -> executablePath at a Chromium-based browser
python main.py          # opens the interactive menu
```

## Where to go next

- New here? See [Installation](Installation).
- Want the flags? See [Usage](Usage).
- Tweaking behavior? See [Configuration](Configuration).
- Something broke? See [Troubleshooting](Troubleshooting).
- Hacking on the code? See [Development](Development).
