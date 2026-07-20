# Configuration

All runtime configuration lives in `config.json` (gitignored — edit your local
copy).

```json
{
  "executablePath": "/usr/bin/chromium",
  "accountFormat": ""
}
```

## `executablePath`

Absolute path to a Chromium-based browser executable. Leave empty to be
prompted on first run.

## `accountFormat`

Controls how credentials are saved. Supported placeholders:

| Placeholder | Meaning |
| --- | --- |
| `{email}` | MEGA account email. |
| `{emailPassword}` | mail.tm inbox password. |
| `{password}` | MEGA account password. |

- `""` (default) → one human-readable JSON file per account under
  `credentials/`.
- A custom string, e.g. `"{email}#{password}"`, writes that format instead.

With `--export-csv`, every account is additionally appended to
`credentials/accounts.csv` as `email,password,emailPassword`.

## In-session settings (menu → Settings)

These are changed at runtime in the menu and are **not** persisted to
`config.json`:

- **Max Attempts** — how many times registration retries with a fresh email.
- **Visible Browser** — headless vs. visible Chromium.
- **Auto CSV Export** — toggle CSV export on/off.
