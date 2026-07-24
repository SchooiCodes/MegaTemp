import pytest

class TestRetry:
	def test_retry_success_first_try(self):
		from utilities.retry import retry

		called = 0

		@retry(max_attempts=3, label="test")
		def fn():
			nonlocal called
			called += 1
			return 42

		assert fn() == 42
		assert called == 1

	def test_retry_eventually_succeeds(self):
		from utilities.retry import retry

		called = 0

		@retry(max_attempts=3, label="test")
		def fn():
			nonlocal called
			called += 1
			if called < 3:
				raise ConnectionError("transient")
			return "ok"

		assert fn() == "ok"
		assert called == 3

	def test_retry_exhausted(self):
		from utilities.retry import retry

		@retry(max_attempts=2, label="test")
		def fn():
			raise ValueError("always fails")

		import pytest as _pt

		with _pt.raises(ValueError):
			fn()


# ======================================================================
# utilities/provider.py — provider registry
# ======================================================================

