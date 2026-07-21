# Configuration

All runtime configuration lives in `config.json` (gitignored — edit your local
copy).

```json
{
  "schemaVersion": 1,
  "executablePath": "/usr/bin/chromium",
  "accountFormat": "",
  "proxy": "",
  "proxyFile": "",
  "proxyPerAttempt": false,
  "maxAttempts": 4,
  "csvExport": false,
  "visibleBrowser": false,
  "emailProvider": "mailtm"
}
```

## `executablePath`

Absolute path to a Chromium-based browser executable. Leave empty to be
prompted on first run. Set via menu: *Settings → Edit Config*.

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

## `proxy` / `proxyFile` / `proxyPerAttempt`

Set a single proxy URL or a file of proxies (one per line). When
`proxyPerAttempt` is `true`, each registration attempt uses the next proxy
from the rotation.

## `maxAttempts`, `csvExport`, `visibleBrowser`

These can be toggled from the TUI menu (*Settings*) and are now persisted to
`config.json` across sessions.

With `--export-csv`, every account is additionally appended to
`credentials/accounts.csv` as `email,password,emailPassword`.

With `--export-jsonl`, every account is appended to
`credentials/accounts.jsonl` as a JSON Line.

## `schemaVersion`

Auto-managed. MegaTemp migrates older configs forward on read. Never edit
this manually.
