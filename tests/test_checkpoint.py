import pytest
import os
import time

class TestCheckpoint:
	def test_save_and_load(self, tmp_path):
		from utilities.etc import (
			save_checkpoint,
			load_checkpoint,
			clear_checkpoint,
			LoopState,
		)

		old = os.getcwd()
		os.chdir(tmp_path)
		state = LoopState(total=50, completed=10, failed=2, started_at=time.monotonic())
		save_checkpoint(state)
		loaded = load_checkpoint()
		assert loaded is not None
		assert loaded.total == 50
		assert loaded.completed == 10
		assert loaded.failed == 2
		clear_checkpoint()
		assert load_checkpoint() is None
		os.chdir(old)

	def test_load_nonexistent(self):
		from utilities.etc import load_checkpoint

		assert load_checkpoint() is None

	def test_clear_no_file(self):
		from utilities.etc import clear_checkpoint

		# Should not raise.
		clear_checkpoint()


# ======================================================================
# web.py
# ======================================================================

