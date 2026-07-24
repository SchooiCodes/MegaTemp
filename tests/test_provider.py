import pytest

class TestProviderRegistry:
	def test_get_provider_unknown(self):
		from utilities.provider import get_provider

		assert get_provider("nonexistent_provider") is None

	def test_get_provider_names_contains_defaults(self):
		from utilities.provider import get_provider_names

		names = get_provider_names()
		assert "mailtm" in names
		assert "guerrillamail" in names

	def test_get_provider_mailtm(self):
		from utilities.provider import get_provider

		prov = get_provider("mailtm")
		assert prov is not None
		assert prov.name == "mailtm"


# ======================================================================
# utilities/etc.py — notify
# ======================================================================

