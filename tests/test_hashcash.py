import pytest

class TestHashcash:
	def test_mega_b64_roundtrip(self):
		from utilities.hashcash import mega_b64encode, mega_b64decode
		data = b"test data 12345"
		assert mega_b64decode(mega_b64encode(data)) == data

	def test_threshold_formula(self):
		from utilities.hashcash import threshold_from_easiness
		assert threshold_from_easiness(0) == 1 << 3
		assert threshold_from_easiness(192) == 1 << 24
		assert threshold_from_easiness(255) == ((63 << 1) + 1) << (3 * 7 + 3)

	def test_solve_challenge_bad_header(self):
		from utilities.hashcash import solve_hashcash_challenge
		import pytest
		with pytest.raises(ValueError, match="invalid X-Hashcash header"):
			solve_hashcash_challenge("garbage")
		with pytest.raises(ValueError, match="unsupported hashcash version"):
			solve_hashcash_challenge("2:1:100:token")

	def test_gencash_known_input(self):
		from utilities.hashcash import gencash
		result = gencash("RUvIePV2PNO8ofg8xp1aT5ugBcKSEzwKoLBw9o4E6F_fmn44eC3oMpv388UtFl2K", 192)
		assert isinstance(result, str)
		assert len(result) == 6  # MEGA-base64 of 4 bytes


if __name__ == "__main__":
	pytest.main([__file__, "-v", "--tb=short"])

