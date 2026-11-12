import base64
import hashlib
import os
import struct
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

TOKEN_BYTES = 48
PREFIX_BYTES = 4
REPEAT = 262144
BUF_SIZE = PREFIX_BYTES + REPEAT * TOKEN_BYTES

_MEGA_B64 = str.maketrans("+/", "-_")

# Total hashcash threads allowed across *all* concurrent solves. Without this
# budget, N parallel workers each spawned 4 threads, so 10 workers fought over
# 40 SHA-256 threads on the same cores. The budget is shared, not per solve.
SOLVE_BUDGET = max(1, min(8, os.cpu_count() or 4))
_budget_free = SOLVE_BUDGET
_budget_lock = threading.Lock()


def _reserve_threads(wanted: int) -> int:
	"""Reserve at least one (and at most *wanted*) solver threads."""
	global _budget_free
	with _budget_lock:
		count = max(1, min(wanted, _budget_free))
		_budget_free -= count
		return count


def _release_threads(count: int) -> None:
	global _budget_free
	with _budget_lock:
		_budget_free = min(SOLVE_BUDGET, _budget_free + count)


def mega_b64encode(data: bytes) -> str:
	return base64.b64encode(data).decode().translate(_MEGA_B64).rstrip("=")


def mega_b64decode(s: str) -> bytes:
	s = s.replace("-", "+").replace("_", "/")
	pad = 4 - len(s) % 4
	if pad != 4:
		s += "=" * pad
	return base64.b64decode(s)


def threshold_from_easiness(e: int) -> int:
	return (((e & 63) << 1) + 1) << ((e >> 6) * 7 + 3)


def _build_buffer(token: bytes) -> bytearray:
	buf = bytearray(BUF_SIZE)
	buf[PREFIX_BYTES : PREFIX_BYTES + TOKEN_BYTES] = token
	filled = TOKEN_BYTES
	while filled < REPEAT * TOKEN_BYTES:
		copy = min(filled, REPEAT * TOKEN_BYTES - filled)
		src = bytes(buf[PREFIX_BYTES : PREFIX_BYTES + filled])
		buf[PREFIX_BYTES + filled : PREFIX_BYTES + filled + copy] = src[:copy]
		filled += copy
	return buf


def _search_worker(
	buf: bytearray, threshold: int, start: int, stride: int, stop
) -> str | None:
	while not stop.is_set():
		n = start
		start += stride
		struct.pack_into(">I", buf, 0, n)
		h = hashlib.sha256(buf).digest()
		word = struct.unpack(">I", h[:4])[0]
		if word <= threshold:
			stop.set()
			return mega_b64encode(struct.pack(">I", n))
	return None


def gencash(
	token_b64: str, easiness: int, timeout_seconds: float = 60.0, max_workers: int = 4
) -> str:
	token = mega_b64decode(token_b64)
	if len(token) != TOKEN_BYTES:
		raise ValueError(f"token must decode to {TOKEN_BYTES} bytes, got {len(token)}")
	threshold = threshold_from_easiness(easiness)
	buf = _build_buffer(token)
	stop = threading.Event()
	workers = _reserve_threads(max_workers)
	pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="hashcash")
	futures = [
		pool.submit(_search_worker, buf, threshold, w, workers, stop)
		for w in range(workers)
	]
	try:
		for f in as_completed(futures, timeout=timeout_seconds):
			result = f.result()
			if result is not None:
				return result
		raise TimeoutError("hashcash solving timed out")
	finally:
		# Always stop the workers: the old code left them spinning forever on
		# the timeout path, and ``shutdown(wait=True)`` then hung the caller.
		stop.set()
		pool.shutdown(wait=False, cancel_futures=True)
		_release_threads(workers)


def solve_hashcash_challenge(header_value: str) -> str:
	parts = header_value.split(":")
	if len(parts) != 4:
		raise ValueError(
			f"invalid X-Hashcash header (expected 4 colon-delimited fields, got {len(parts)}): {header_value}"
		)
	version = int(parts[0])
	if version != 1:
		raise ValueError(f"unsupported hashcash version: {version}")
	easiness_str, timestamp_str, token_b64 = parts[1], parts[2], parts[3]
	try:
		easiness = int(easiness_str)
	except ValueError:
		raise ValueError(
			f"invalid easiness value in X-Hashcash: {easiness_str}"
		) from None
	try:
		int(timestamp_str)
	except ValueError:
		raise ValueError(f"invalid timestamp in X-Hashcash: {timestamp_str}") from None
	if not (0 <= easiness <= 255):
		raise ValueError(f"easiness out of range (0-255): {easiness}")
	return gencash(token_b64, easiness)
