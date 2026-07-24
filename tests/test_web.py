import pytest

class TestWeb:
	def test_set_verbose(self):
		import utilities.web

		utilities.web.set_verbose(True)
		assert utilities.web._VERBOSE is True
		utilities.web.set_verbose(False)
		assert utilities.web._VERBOSE is False

	def test_get_random_string_default(self):
		from utilities.web import get_random_string

		s = get_random_string(14)
		assert len(s) == 14
		assert all(c.isalnum() for c in s)

	def test_get_random_string_various_lengths(self):
		from utilities.web import get_random_string

		for length in [1, 10, 50, 100]:
			s = get_random_string(length)
			assert len(s) == length

	def test_get_random_string_no_empty(self):
		from utilities.web import get_random_string

		s = get_random_string(0)
		assert s == ""


# ======================================================================
# menu.py
# ======================================================================

