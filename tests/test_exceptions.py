import pytest

class TestExceptions:
	def test_base_exception(self):
		from utilities.exceptions import MegaTempError
		err = MegaTempError("test")
		assert str(err) == "test"
		assert issubclass(MegaTempError, Exception)

	def test_registration_error(self):
		from utilities.exceptions import RegistrationError, MegaTempError
		assert issubclass(RegistrationError, MegaTempError)

	def test_config_error(self):
		from utilities.exceptions import ConfigError, MegaTempError
		assert issubclass(ConfigError, MegaTempError)

	def test_proxy_error(self):
		from utilities.exceptions import ProxyError, MegaTempError
		assert issubclass(ProxyError, MegaTempError)

	def test_email_provider_error(self):
		from utilities.exceptions import EmailProviderError, MegaTempError
		assert issubclass(EmailProviderError, MegaTempError)

	def test_browser_error(self):
		from utilities.exceptions import BrowserError, MegaTempError
		assert issubclass(BrowserError, MegaTempError)

	def test_api_error(self):
		from utilities.exceptions import APIError, MegaTempError
		assert issubclass(APIError, MegaTempError)

	def test_account_error(self):
		from utilities.exceptions import AccountError, MegaTempError
		assert issubclass(AccountError, MegaTempError)


# ======================================================================
# password_strength.py — generate_password
# ======================================================================

