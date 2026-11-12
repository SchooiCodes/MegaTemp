"""Best-effort inter-process advisory locks for shared state files.

Credential stores (``accounts.txt``, ``accounts.csv``, ``accounts.jsonl``) are
append-only and shared by every worker. With ``--isolate`` each worker is a
separate process, so a plain ``open(..., "a")`` can interleave partial lines.
Wrapping the write in :func:`locked` serialises writers across processes and
threads without changing the file format.

The lock is advisory and only protects code that opts in. Lock files live next
to the protected file as ``<path>.lock`` and are never deleted (they are tiny
and deleting them would reintroduce a race).
"""

import os
import time
from contextlib import contextmanager

if os.name == "nt":
	import msvcrt

	def _try_lock(fh) -> bool:
		try:
			fh.seek(0)
			msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
			return True
		except OSError:
			return False

	def _unlock(fh) -> None:
		try:
			fh.seek(0)
			msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
		except OSError:
			pass

else:
	import fcntl

	def _try_lock(fh) -> bool:
		try:
			fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
			return True
		except OSError:
			return False

	def _unlock(fh) -> None:
		try:
			fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
		except OSError:
			pass


@contextmanager
def locked(path: str, timeout: float = 30.0):
	"""Hold an exclusive lock for *path* while the block runs.

	Raises ``TimeoutError`` if the lock cannot be acquired within *timeout*
	seconds, so a stuck worker can never hang a batch forever.
	"""
	lock_path = f"{path}.lock"
	parent = os.path.dirname(lock_path)
	if parent:
		os.makedirs(parent, exist_ok=True)

	fh = open(lock_path, "a+b")
	try:
		deadline = time.monotonic() + timeout
		while not _try_lock(fh):
			if time.monotonic() >= deadline:
				raise TimeoutError(f"timed out waiting for lock on {path}")
			time.sleep(0.05)
		try:
			yield
		finally:
			_unlock(fh)
	finally:
		fh.close()
