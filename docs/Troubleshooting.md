# Troubleshooting

## "invalid email or password" when I log in

This was the original upstream bug. MegaTemp's `_robust_type` (in
`utilities/web.py`) types the password with a per-character delay and verifies
the field value, so dead accounts are no longer saved. If you still hit this,
make sure you are using the **latest** MegaTemp and not an old build.

## The browser opens but the page is blank / has no inputs

MEGA sometimes serves an empty registration page when it rate-limits or blocks
an IP (e.g. after many signups from one address). The symptom is the form
failing to render (`#register-firstname` never appears). This is
**environmental**, not a code bug — wait a few hours or try a different network
and retry.

## Confirmation email never arrives

mail.tm delivery is occasionally delayed or dropped. MegaTemp polls for the
confirmation email with a bounded retry, then retries the whole registration
with a fresh email. If it still fails after the configured attempts, it reports
failure and exits cleanly rather than hanging.

## Chromium fails to launch / "Browser closed unexpectedly"

On Linux, Chromium needs sandbox-disabling flags. MegaTemp already adds
`--no-sandbox --disable-setuid-sandbox --disable-gpu --disable-dev-shm-usage`.
If launch still fails, verify `executablePath` points at a real browser binary
and that `/dev/shm` is not full.

## Reading the logs

Pass `-v` (or enable Verbose in the menu) to see every phase:

```
[mail] generated address: scornfulzebra@web-library.net
[register] opening mega.nz/register ...
[register] name + email filled in.
Registered account successfully!
[register] submitting registration form ...
[mail] confirmation email received.
[confirm] account created.
Account verified in 28.0s.
Verified account.
```

Each phase is prefixed with a `[tag]` so you can see exactly where a run stops.

## Encrypted credentials not readable

If you set `--encryption-password` (or config `encryptionPassword`) and later
try to read credentials in the viewer, health dashboard, or keepalive, the
system auto-detects encrypted fields and decrypts them transparently. If you
**change** the password after saving encrypted credentials, the old ones will be
unreadable — keep your encryption password consistent. Decryption errors
produce clear "Failed to decrypt field" warnings rather than silent data loss.

## Email provider fallback not working

Provider fallback triggers automatically: if all attempts with the primary
provider (e.g. `mailtm`) fail, `register()` switches to the alternative
provider (`guerrillamail`). You can also force a specific provider with
`--provider NAME`. Fallback is logged with "Switching to fallback provider."

## Proxy auto-fetch returns no proxies

`--proxy-url URL` expects a plain-text list (one proxy per line) or a JSON array
of proxy strings. Empty lines and `#` comments in plain-text lists are skipped.
If the URL is unreachable or the format is unexpected, a warning is printed and
no proxies are added to the rotation.

## Webhook not firing

Webhooks are fire-and-forget with a 10-second timeout. If the target URL is
unreachable, the error is silently swallowed. Verify the URL is correct and
publicly accessible. The `--quiet` flag suppresses webhook POSTs.
