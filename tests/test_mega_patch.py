"""Tests for the faster MEGA upload patch in utilities/mega_patch.py."""

import random
from types import SimpleNamespace


class TestFastChunks:
	def test_small_file_single_chunk(self):
		from utilities.mega_patch import _fast_chunks
		assert list(_fast_chunks(100)) == [(0, 100)]

	def test_empty_file(self):
		from utilities.mega_patch import _fast_chunks
		assert list(_fast_chunks(0)) == [(0, 0)]

	def test_exact_multiple_of_chunk_size(self):
		from utilities.mega_patch import _FAST_CHUNK_SIZE, _fast_chunks
		size = _FAST_CHUNK_SIZE * 2
		assert list(_fast_chunks(size)) == [
			(0, _FAST_CHUNK_SIZE),
			(_FAST_CHUNK_SIZE, _FAST_CHUNK_SIZE),
		]

	def test_contiguous_coverage(self):
		from utilities.mega_patch import _FAST_CHUNK_SIZE, _fast_chunks
		for size in [1, 17, _FAST_CHUNK_SIZE + 1, _FAST_CHUNK_SIZE * 3 + 12345]:
			chunks = list(_fast_chunks(size))
			assert chunks[0][0] == 0
			assert chunks[-1][0] + chunks[-1][1] == size
			for i in range(len(chunks) - 1):
				assert chunks[i][0] + chunks[i][1] == chunks[i + 1][0]
			for _start, csize in chunks:
				assert 0 <= csize <= _FAST_CHUNK_SIZE


class TestUploadPatch:
	def test_patch_mega_registers_upload(self, monkeypatch):
		from mega import Mega
		import utilities.mega_patch as mp

		original_upload = Mega.upload
		mp.patch_mega()
		assert Mega.upload is not original_upload
		assert Mega.upload.__name__ == "wrapper"

	def _reference_payloads_and_mac(self, data, ul_key):
		"""Stock mega.py upload crypto, computed independently."""
		from Crypto.Cipher import AES
		from Crypto.Util import Counter
		from mega.crypto import a32_to_str, get_chunks, makebyte, str_to_a32

		file_size = len(data)
		k_str = a32_to_str(ul_key[:4])
		init_counter = ((ul_key[4] << 32) + ul_key[5]) << 64
		count = Counter.new(128, initial_value=init_counter)
		aes = AES.new(k_str, AES.MODE_CTR, counter=count)
		mac_str = b"\0" * 16
		mac_encryptor = AES.new(k_str, AES.MODE_CBC, mac_str)
		iv_str = a32_to_str([ul_key[4], ul_key[5], ul_key[4], ul_key[5]])

		payloads = []
		if file_size > 0:
			for chunk_start, chunk_size in get_chunks(file_size):
				chunk = data[chunk_start : chunk_start + chunk_size]
				encryptor = AES.new(k_str, AES.MODE_CBC, iv_str)
				for i in range(0, len(chunk) - 16, 16):
					encryptor.encrypt(chunk[i : i + 16])
				if file_size > 16:
					i += 16
				else:
					i = 0
				block = chunk[i : i + 16]
				if len(block) % 16:
					block += makebyte("\0" * (16 - len(block) % 16))
				mac_str = mac_encryptor.encrypt(encryptor.encrypt(block))
				payloads.append(aes.encrypt(chunk))
		else:
			payloads.append(b"")

		file_mac = str_to_a32(mac_str)
		meta_mac = (file_mac[0] ^ file_mac[1], file_mac[2] ^ file_mac[3])
		return payloads, meta_mac

	def _run_upload(self, tmp_path, monkeypatch, data, ul_key):
		import requests
		from utilities.mega_patch import _patch_upload

		file_path = tmp_path / "upload.bin"
		file_path.write_bytes(data)

		class FakeResp:
			def __init__(self, text):
				self.text = text

			def raise_for_status(self):
				pass

		class FakeSession:
			instances = 0
			all_posts = []

			def __init__(self):
				type(self).instances += 1
				self.posts = []

			def post(self, url, data, timeout):
				self.posts.append((url, data))
				type(self).all_posts.append((url, data))
				return FakeResp("handle-" + url.rsplit("/", 1)[-1])

			def close(self):
				pass

		monkeypatch.setattr(requests, "Session", FakeSession)

		api_calls = []

		def fake_api_request(payload):
			api_calls.append(payload)
			if isinstance(payload, dict) and payload.get("a") == "u":
				return {"p": "https://upload.example/ul"}
			return {"ok": True}

		fake_mega = SimpleNamespace(
			root_id="ROOT",
			timeout=5,
			request_id="REQ1",
			master_key=[0x01020304, 0x05060708, 0x090A0B0C, 0x0D0E0F10],
			_api_request=fake_api_request,
		)

		it = iter(ul_key)
		monkeypatch.setattr(random, "randint", lambda a, b: next(it))

		wrapper = _patch_upload(lambda *a, **k: None)
		wrapper(fake_mega, str(file_path), dest="ROOT")
		return FakeSession, api_calls

	def test_upload_single_session_and_payload_parity(self, tmp_path, monkeypatch):
		data = bytes((i * 13 + 5) % 256 for i in range(131089))
		ul_key = [
			0x11111111, 0x22222222, 0x33333333,
			0x44444444, 0x55555555, 0x66666666,
		]

		FakeSession, api_calls = self._run_upload(tmp_path, monkeypatch, data, ul_key)
		expected_payloads, expected_meta = self._reference_payloads_and_mac(data, ul_key)

		from mega.crypto import get_chunks
		chunks = list(get_chunks(len(data)))

		posts = FakeSession.all_posts
		assert len(posts) == len(chunks)
		assert FakeSession.instances == 1, "must reuse a single persistent session"

		# Chunks upload in parallel, so completion order is not guaranteed.
		# Key by chunk start extracted from the URL.
		by_start = {}
		for url, payload in posts:
			start = int(url.rsplit("/", 1)[-1])
			assert url == "https://upload.example/ul/" + str(start)
			by_start[start] = payload

		assert set(by_start) == {start for start, _ in chunks}
		for (start, _size), expected in zip(chunks, expected_payloads, strict=True):
			assert by_start[start] == expected, "payload bytes must match stock upload"

		completion = next(c for c in api_calls if isinstance(c, dict) and c.get("a") == "p")
		last_start = chunks[-1][0]
		assert completion["n"][0]["h"] == "handle-" + str(last_start)

	def test_upload_empty_file(self, tmp_path, monkeypatch):
		data = b""
		ul_key = [
			0x11111111, 0x22222222, 0x33333333,
			0x44444444, 0x55555555, 0x66666666,
		]
		FakeSession, api_calls = self._run_upload(tmp_path, monkeypatch, data, ul_key)

		expected_payloads, expected_meta = self._reference_payloads_and_mac(data, ul_key)
		posts = FakeSession.all_posts
		assert len(posts) == 1
		assert posts[0][0] == "https://upload.example/ul/0"
		assert posts[0][1] == b""

	def test_upload_small_file_matches_reference(self, tmp_path, monkeypatch):
		data = bytes((i * 7 + 3) % 256 for i in range(100))
		ul_key = [
			0xAAAA1111, 0xBBBB2222, 0xCCCC3333,
			0xDDDD4444, 0xEEEE5555, 0xFFFF6666,
		]
		FakeSession, api_calls = self._run_upload(tmp_path, monkeypatch, data, ul_key)
		expected_payloads, expected_meta = self._reference_payloads_and_mac(data, ul_key)
		actual_payloads = [payload for _url, payload in FakeSession.all_posts]
		assert actual_payloads == expected_payloads
