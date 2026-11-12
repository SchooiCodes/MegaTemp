"""Tests for the cross-process credential file lock."""

import threading
import time

import pytest

from utilities.filelock import locked


def test_serialises_threads(tmp_path):
	path = tmp_path / "counter.txt"
	path.write_text("0")

	def bump():
		for _ in range(10):
			with locked(str(path)):
				value = int(path.read_text())
				time.sleep(0.001)
				path.write_text(str(value + 1))

	threads = [threading.Thread(target=bump) for _ in range(5)]
	for thread in threads:
		thread.start()
	for thread in threads:
		thread.join()

	assert path.read_text() == "50"


def test_timeout_when_lock_is_held(tmp_path):
	path = str(tmp_path / "held.txt")
	ready = threading.Event()
	release = threading.Event()

	def holder():
		with locked(path):
			ready.set()
			release.wait(5)

	thread = threading.Thread(target=holder)
	thread.start()
	assert ready.wait(5)
	try:
		with pytest.raises(TimeoutError):
			with locked(path, timeout=0.1):
				pass
	finally:
		release.set()
		thread.join()
