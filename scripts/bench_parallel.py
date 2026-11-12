"""Benchmark the in-process parallel scheduler without touching MEGA.

Run:  python scripts/bench_parallel.py --workers 5 --accounts 5

The fake browser and fake registration remove all network/browser noise, so
the numbers measure scheduling only: how fast workers start and whether the
batch wall time tracks the slowest worker instead of the sum.
"""

import argparse
import asyncio
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utilities import console  # noqa: E402

console.init()

import main  # noqa: E402

_START = 0.0
_STARTS: list[float] = []
_ENDS: list[float] = []


class _FakeBrowser:
	async def close(self):
		pass


async def _fake_launch(_kwargs):
	return _FakeBrowser()


async def _fake_register(*_args, **_kwargs):
	_STARTS.append(time.monotonic() - _START)
	await asyncio.sleep(random.uniform(4, 12))
	_ENDS.append(time.monotonic() - _START)
	sys.exit(0)


def run(workers: int, accounts: int) -> int:
	global _START

	main._launch_browser = _fake_launch
	main._cleanup_pyppeteer = lambda _browser: None
	main.register = _fake_register
	main._proxy_manager = None

	_START = time.monotonic()
	try:
		main.parallel_registrations(
			accounts,
			"fake-browser",
			main.Config(),
			parallelism=workers,
		)
	except SystemExit:
		pass
	except Exception as exc:  # noqa: BLE001 - benchmark should report, not crash
		print(f"benchmark failed: {exc}")
		return 1

	wall = time.monotonic() - _START
	spread = max(_STARTS) - min(_STARTS) if _STARTS else 0.0
	print(
		f"wall={wall:.2f}s start-spread={spread:.2f}s finished={len(_ENDS)}/{accounts}"
	)
	return 0 if len(_ENDS) == accounts and spread < 1.0 else 1


if __name__ == "__main__":
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("--workers", type=int, default=5)
	parser.add_argument("--accounts", type=int, default=5)
	args = parser.parse_args()
	raise SystemExit(run(args.workers, args.accounts))
