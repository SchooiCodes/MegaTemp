"""Password strength estimation (entropy-based)."""

import math
import re


def estimate_entropy(password: str) -> float:
	"""Estimate Shannon entropy of a password in bits."""
	if not password:
		return 0.0
	# Build the character set estimate
	pool = 0
	if re.search(r"[a-z]", password):
		pool += 26
	if re.search(r"[A-Z]", password):
		pool += 26
	if re.search(r"[0-9]", password):
		pool += 10
	if re.search(r"[^a-zA-Z0-9]", password):
		pool += 32  # rough estimate for special chars
	if pool == 0:
		return 0.0
	return len(password) * math.log2(pool)


def strength_label(password: str) -> tuple[str, str]:
	"""Return (label, colour_code) for password strength.

	Labels: Very Weak, Weak, Medium, Strong, Very Strong.
	"""
	bits = estimate_entropy(password)
	if bits < 30:
		return "Very Weak", "\033[91m"  # red
	if bits < 50:
		return "Weak", "\033[93m"  # yellow
	if bits < 70:
		return "Medium", "\033[96m"  # cyan
	if bits < 90:
		return "Strong", "\033[92m"  # green
	return "Very Strong", "\033[95m"  # purple
