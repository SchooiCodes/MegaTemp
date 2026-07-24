# AGENTS

This file documents recurring tasks and patterns for MegaTemp development.
It is loaded on every agent invocation.

## Quick reference

```bash
# run tests
python -m pytest tests/ -q --tb=short

# number of tests
python -m pytest tests/ --collect-only -q | tail -1

# run the tool
python main.py --version
python main.py --health --json
python main.py --help
```

## Known issues to watch

- tenacity's asyncio.coroutine was removed in Python 3.11. Fixed by `utilities/compat.py` (loaded via `main.py`).
- The `snip` tool intercepts `print()` inside Python `-c` strings causing SyntaxError — avoid `snip print()` inside `-c` blocks.
- `services/download.py` uses threading-based timeout (not SIGALRM) for Windows compatibility.
- `services/upload.py` uses `threading.Lock` for thread-safe session cache.
- `utilities/fs.py` provides `CREDENTIALS_DIR` and `CREDENTIALS_TXT` constants — import, don't hardcode `"./credentials"` or `"credentials.txt"`.
- `_cleanup_pyppeteer()` goes outside the `try` block so it runs even if `browser.close()` raises.
- `register()` cleanup order: page → context → browser, in nested finally blocks.
- `services/account.py` `delete_default()` uses cached `get_mega_session()` — don't create fresh `Mega()` instances.
- `services/extract.py` export functions unified via `_export_csv(headers, row_fn, filename)`.

## Hashcash (MEGA PoW) fix

- **Problem**: Some MEGA accounts trigger HTTP 402 + `X-Hashcash` response header. The `mega.py` library crashed with `JSONDecodeError` because the empty 402 body couldn't be parsed.
- **Solution**: `utilities/mega_patch.py` monkey-patches `Mega._api_request` at import time (called from `main.py`). Detects 402, solves PoW, retries with `X-Hashcash` header. No modification to installed `mega.py` needed.
- **Solver**: `utilities/hashcash.py` replicates MEGA SDK algorithm: 12,582,916 byte buffer (4-byte prefix + 262144 copies of 48-byte token), finds 4-byte big-endian nonce where first 32 bits of SHA-256(hash) ≤ threshold.
- **Threshold formula**: `easiness=192` → `(((192&63)<<1)+1) << ((192>>6)*7+3)` = `1<<24` = 16777216 (0.39% of hash space, ~256 attempts avg).
- **Header format**: Response `X-Hashcash: 1:192:1731410499:RUvIePV2PNO8ofg8xp1aT5ugBcKSEzwKoLBw9o4E6F_fmn44eC3oMpv388UtFl2K` → Retry `X-Hashcash: 1:RUvIePV2PNO8ofg8xp1aT5ugBcKSEzwKoLBw9o4E6F_fmn44eC3oMpv388UtFl2K:AAAA4A`. Solution is MEGA-base64 of 4-byte big-endian nonce (6 chars).
- **Files**:
  - `utilities/hashcash.py` — solver (standalone, `gencash()` + `solve_hashcash_challenge()`)
  - `utilities/mega_patch.py` — monkey-patch wrapper injecting 402 handling into `Mega._api_request`
- **Status**: 4 hashcash-challenged accounts (mtvw3txvjtmjtt, mtalsvpwuveiig, mtekdei3ojicf3, mtpsm30fgxumr4) accept the PoW (402→200), but MEGA API returns `-9` (ENOENT) suggesting suspended accounts. 15 non-hashcash accounts work normally.
