from utilities.hashcash import solve_hashcash_challenge
from mega.errors import RequestError


def _patch_api_request(original_method):
	def wrapper(self, data):
		import json
		import requests

		params = {"id": self.sequence_num}
		self.sequence_num += 1
		if self.sid:
			params.update({"sid": self.sid})
		if not isinstance(data, list):
			data = [data]

		url = f"{self.schema}://g.api.{self.domain}/cs"
		response = requests.post(
			url,
			params=params,
			data=json.dumps(data),
			timeout=self.timeout,
		)

		if response.status_code == 402:
			hc_header = response.headers.get("X-Hashcash")
			if not hc_header:
				raise RequestError("HTTP 402 without X-Hashcash header")
			solution = solve_hashcash_challenge(hc_header)
			token = hc_header.split(":", 3)[3]
			headers = {"X-Hashcash": f"1:{token}:{solution}"}
			response = requests.post(
				url,
				params=params,
				headers=headers,
				data=json.dumps(data),
				timeout=self.timeout,
			)

		json_resp = json.loads(response.text)
		try:
			if isinstance(json_resp, list):
				int_resp = json_resp[0] if isinstance(json_resp[0], int) else None
			elif isinstance(json_resp, int):
				int_resp = json_resp
			else:
				int_resp = None
		except (IndexError, TypeError):
			int_resp = None

		if int_resp is not None:
			if int_resp == -3:
				raise RuntimeError("Request failed, retrying")
			raise RequestError(int_resp, response.status_code)
		return json_resp[0]

	return wrapper


# Maximum upload chunk size allowed by the MEGA protocol.
_FAST_CHUNK_SIZE = 0x400000  # 4 MiB


def _fast_chunks(size, chunk_size=_FAST_CHUNK_SIZE):
	"""Yield (start, size) pairs covering ``size`` bytes in ``chunk_size`` steps.

	NOTE: not used by the upload patch — MEGA's file MAC chain is bound to the
	canonical chunk partition (see `mega.crypto.get_chunks`), so changing chunk
	boundaries invalidates the MAC and makes files fail integrity checks on
	download. Kept only for reference/tests.
	"""
	p = 0
	while p + chunk_size < size:
		yield (p, chunk_size)
		p += chunk_size
	yield (p, size - p)


def _patch_upload(original_method):
	"""Replace Mega.upload with a faster, semantically-identical upload.

	The stock implementation POSTs every chunk sequentially and opens a
	brand-new connection for each one (top-level ``requests.post`` creates a
	fresh Session every call). This version:
	  * reuses a single persistent ``requests.Session`` (keep-alive), and
	  * uploads chunks in parallel via a thread pool (MEGA's own client does
	    the same).

	Chunk boundaries are kept exactly as ``mega.crypto.get_chunks`` — the file
	MAC chain is sensitive to the chunk partition, and the downloader
	(``Mega.download``) recomputes it with the same boundaries and rejects
	files whose MAC does not match. Encryption and MAC output are therefore
	byte-for-byte identical to the original: each chunk is CTR-encrypted with a
	counter positioned at its byte offset (so the chunk streams combine into
	the same ciphertext), and the file MAC chain is replayed sequentially after
	the parallel phase.
	"""

	def wrapper(self, filename, dest=None, dest_filename=None):
		import os
		import random
		from concurrent.futures import ThreadPoolExecutor
		import requests
		from Crypto.Cipher import AES
		from Crypto.Util import Counter
		from mega.crypto import (
			a32_to_str,
			str_to_a32,
			makebyte,
			get_chunks,
			base64_url_encode,
			encrypt_attr,
			encrypt_key,
			a32_to_base64,
		)

		# determine storage node
		if dest is None:
			if not hasattr(self, "root_id"):
				self.get_files()
			dest = self.root_id

		with open(filename, "rb"):
			file_size = os.path.getsize(filename)
			ul_url = self._api_request({"a": "u", "s": file_size})["p"]

			# generate random aes key (128) for file
			ul_key = [random.randint(0, 0xFFFFFFFF) for _ in range(6)]
			k_str = a32_to_str(ul_key[:4])
			init_counter = ((ul_key[4] << 32) + ul_key[5]) << 64

			mac_str = b"\0" * 16
			mac_encryptor = AES.new(k_str, AES.MODE_CBC, mac_str)
			iv_str = a32_to_str([ul_key[4], ul_key[5], ul_key[4], ul_key[5]])

			chunks = list(get_chunks(file_size))

			encrypted_blocks = [None] * len(chunks)
			last_index = len(chunks) - 1
			session = requests.Session()

			def _upload_one(idx):
				chunk_start, chunk_size = chunks[idx]
				with open(filename, "rb") as fh:
					fh.seek(chunk_start)
					chunk = fh.read(chunk_size)

				if file_size > 0:
					# last CBC block of this chunk, used for the file MAC chain
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
					encrypted_blocks[idx] = encryptor.encrypt(block)

					# CTR-encrypt with the counter positioned at this chunk
					count = Counter.new(
						128, initial_value=init_counter + (chunk_start >> 4)
					)
					aes = AES.new(k_str, AES.MODE_CTR, counter=count)
					payload = aes.encrypt(chunk)
				else:
					payload = b""

				resp = session.post(
					ul_url + "/" + str(chunk_start),
					data=payload,
					timeout=self.timeout,
				)
				resp.raise_for_status()
				return resp.text

			try:
				with ThreadPoolExecutor(
					max_workers=min(8, max(1, len(chunks)))
				) as pool:
					handles = list(pool.map(_upload_one, range(len(chunks))))
			finally:
				session.close()

			completion_file_handle = handles[last_index]

			# replay the sequential MAC chain over per-chunk last blocks
			for eb in encrypted_blocks:
				if eb is not None:
					mac_str = mac_encryptor.encrypt(eb)

		file_mac = str_to_a32(mac_str)
		meta_mac = (file_mac[0] ^ file_mac[1], file_mac[2] ^ file_mac[3])

		dest_filename = dest_filename or os.path.basename(filename)
		attribs = {"n": dest_filename}
		encrypt_attribs = base64_url_encode(encrypt_attr(attribs, ul_key[:4]))
		key = [
			ul_key[0] ^ ul_key[4],
			ul_key[1] ^ ul_key[5],
			ul_key[2] ^ meta_mac[0],
			ul_key[3] ^ meta_mac[1],
			ul_key[4],
			ul_key[5],
			meta_mac[0],
			meta_mac[1],
		]
		encrypted_key = a32_to_base64(encrypt_key(key, self.master_key))

		data = self._api_request(
			{
				"a": "p",
				"t": dest,
				"i": self.request_id,
				"n": [
					{
						"h": completion_file_handle,
						"t": 0,
						"a": encrypt_attribs,
						"k": encrypted_key,
					}
				],
			}
		)
		return data

	return wrapper


def patch_mega():
	from mega import Mega

	Mega._api_request = _patch_api_request(Mega._api_request)
	Mega.upload = _patch_upload(Mega.upload)
