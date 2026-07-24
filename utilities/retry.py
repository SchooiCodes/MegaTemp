"""Network retry wrapper for MEGA and mail API calls.

Uses tenacity with exponential backoff to survive transient network
errors.  All retries log a warning so the user knows what's happening.
"""

import functools
import time

from utilities.etc import p_print, Colours

# ---------------------------------------------------------------------------
# Minimal retry with exponential backoff (no tenacity dependency needed).
# If tenacity is available we use it; otherwise a simple loop.
# ---------------------------------------------------------------------------

import utilities.compat  # noqa: F401 — restores asyncio.coroutine for tenacity

try:
	import tenacity

	_HAS_TENACITY = True
except ImportError:
	_HAS_TENACITY = False


def _log_retry(attempt: int, exc: Exception, label: str):
	p_print(
		f"[retry] {label} attempt {attempt} failed: {exc}. Retrying...",
		Colours.WARNING,
	)


class retry:
	"""Decorator for retrying a function on exceptions.

	Usage::

	    @retry(max_attempts=3, label="MEGA login")
	    def login(): ...
	"""

	def __init__(
		self,
		max_attempts: int = 3,
		base_delay: float = 1.0,
		max_delay: float = 10.0,
		label: str = "",
		exceptions: tuple = (Exception,),
	):
		self.max_attempts = max_attempts
		self.base_delay = base_delay
		self.max_delay = max_delay
		self.label = label
		self.exceptions = exceptions

		if _HAS_TENACITY and self.max_attempts > 1:

			def _before(retry_state):
				if retry_state.attempt_number < self.max_attempts:
					_log_retry(
						retry_state.attempt_number,
						retry_state.outcome.exception(),
						self.label or "call",
					)

			self._tenacity_decorator = tenacity.retry(
				stop=tenacity.stop_after_attempt(self.max_attempts),
				wait=tenacity.wait_exponential(
					multiplier=self.base_delay, max=self.max_delay
				),
				retry=tenacity.retry_if_exception_type(self.exceptions),
				before_sleep=_before,
				reraise=True,
			)
		else:
			self._tenacity_decorator = None

	def __call__(self, func):
		if self._tenacity_decorator is not None:
			return self._tenacity_decorator(func)

		@functools.wraps(func)
		def wrapper(*args, **kwargs):
			last_exc = None
			for attempt in range(1, self.max_attempts + 1):
				try:
					return func(*args, **kwargs)
				except self.exceptions as e:
					last_exc = e
					if attempt < self.max_attempts:
						_log_retry(attempt, e, self.label or func.__name__)
						delay = min(
							self.base_delay * (2 ** (attempt - 1)), self.max_delay
						)
						time.sleep(delay)
			raise last_exc  # type: ignore

		return wrapper
