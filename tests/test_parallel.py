"""Tests for the process-isolated worker pool."""

import pool_target

from utilities.parallel import run_pool


def test_claims_exactly_total():
	successes, failures = run_pool(pool_target.succeed, 2, 5, [{}, {}])
	assert (successes, failures) == (5, 0)


def test_zero_work_exits_immediately():
	successes, failures = run_pool(pool_target.succeed, 2, 0, [{}, {}])
	assert (successes, failures) == (0, 0)
