# Configuration

All runtime configuration lives in `config.json` (gitignored — edit your local
copy).

```json
{
  "schemaVersion": 3,
  "executablePath": "/usr/bin/chromium",
  "accountFormat": "",
  "proxy": "",
  "proxyFile": "",
  "proxyPerAttempt": false,
  "maxAttempts": 4,
  "csvExport": false,
  "jsonlExport": false,
  "visibleBrowser": false,
  "emailProvider": "mailtm",
  "mailTimeout": 120,
  "quiet": false,
  "webhookUrl": "",
  "encryptionPassword": ""
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

## `jsonlExport`

When `true`, every newly-created account is also appended to
`credentials/accounts.jsonl` (one JSON object per line). Can be toggled from
the TUI menu (*Settings → Auto JSONL Export*).

## `mailTimeout`

Maximum seconds to wait for the MEGA confirmation email before retrying.
Default: `120`. Set via `--mail-timeout`.

## `quiet`

When `true`, non-essential output is suppressed (useful for scripting).
Default: `false`. Set via `--quiet`.

## `webhookUrl`

A URL that receives a POST request with a JSON payload on every registration
success (`event: "registration_success"`) or failure
(`event: "registration_failed"`). Set via `--webhook-url`.

## `encryptionPassword`

When set, passwords stored in credential JSON files are encrypted at rest
using Fernet symmetric encryption (requires the `cryptography` Python package).
Reads are automatically decrypted when this password is configured.
Set via `--encryption-password`.

## `schemaVersion`

Auto-managed. MegaTemp migrates older configs forward on read. Never edit
this manually.

### Profiles

Use `--profile NAME` to use `config-{NAME}.json` instead of `config.json`.
This lets you maintain multiple independent configurations for different
environments or use cases.
