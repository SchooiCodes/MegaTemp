"""Custom exception hierarchy for MegaTemp."""


class MegaTempError(Exception):
	"""Base exception for all MegaTemp errors."""


class RegistrationError(MegaTempError):
	"""Raised when account registration fails."""


class ConfigError(MegaTempError):
	"""Raised when config validation or access fails."""


class CredentialError(MegaTempError):
	"""Raised when credential storage/retrieval fails."""


class ProxyError(MegaTempError):
	"""Raised when proxy configuration or testing fails."""


class EmailProviderError(MegaTempError):
	"""Raised when email provider (mail.tm / Guerrilla Mail) fails."""


class BrowserError(MegaTempError):
	"""Raised when browser automation fails."""


class APIError(MegaTempError):
	"""Raised when MEGA API call fails."""


class AccountError(MegaTempError):
	"""Raised when account management operations fail."""
