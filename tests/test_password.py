import pytest

class TestPasswordStrength:
	def test_entropy_empty(self):
		from utilities.password_strength import estimate_entropy

		assert estimate_entropy("") == 0.0

	def test_entropy_non_empty(self):
		from utilities.password_strength import estimate_entropy

		assert estimate_entropy("abc") > 0

	def test_strength_labels(self):
		from utilities.password_strength import strength_label

		label, colour = strength_label("a")
		assert label in ("Very Weak", "Weak", "Medium", "Strong", "Very Strong")
		assert colour.startswith("\033[")

	def test_strong_password(self):
		from utilities.password_strength import strength_label

		label, _ = strength_label("Tr0ub4dor&3!@#xYzQwerty123!!!")
		assert label in ("Strong", "Very Strong")


# ======================================================================
# utilities/retry.py
# ======================================================================

class TestPasswordGenerator:
	def test_generate_password_length(self):
		from utilities.password_strength import generate_password

		pw = generate_password(24)
		assert len(pw) == 24

	def test_generate_password_min_length(self):
		from utilities.password_strength import generate_password

		pw = generate_password(3)
		assert len(pw) >= 8  # clamped to minimum

	def test_generate_password_has_digits_and_special(self):
		from utilities.password_strength import generate_password

		pw = generate_password(32)
		assert any(c.isdigit() for c in pw)
		assert any(not c.isalnum() for c in pw)

	def test_generate_password_unique(self):
		from utilities.password_strength import generate_password

		pw1 = generate_password(20)
		pw2 = generate_password(20)
		assert pw1 != pw2


# ======================================================================
# etc.py — proxy testing, quiet mode
# ======================================================================

