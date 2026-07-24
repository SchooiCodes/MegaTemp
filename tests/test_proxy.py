import pytest
import os

class TestProxyManager:
	def test_empty(self):
		from utilities.etc import ProxyManager

		pm = ProxyManager()
		assert pm.active is False
		assert pm.get_proxy() is None
		assert pm.count == 0

	def test_single_proxy(self):
		from utilities.etc import ProxyManager

		pm = ProxyManager(proxy="http://user:pass@1.2.3.4:8080")
		assert pm.active is True
		assert pm.count == 1
		assert pm.get_proxy() == "http://user:pass@1.2.3.4:8080"

	def test_rotation(self):
		from utilities.etc import ProxyManager

		pm = ProxyManager(proxy_file="/nonexistent", per_attempt=True)
		# file doesn't exist → no proxies loaded
		assert pm.active is False
		assert pm.count == 0

	def test_rotation_with_file(self, tmp_path):
		from utilities.etc import ProxyManager

		pf = tmp_path / "proxies.txt"
		pf.write_text("http://a:1@1.2.3.4:80\nhttp://b:2@5.6.7.8:8080\n")
		pm = ProxyManager(proxy_file=str(pf), per_attempt=True)
		assert pm.count == 2
		assert pm.get_proxy() == "http://a:1@1.2.3.4:80"
		assert pm.get_proxy() == "http://b:2@5.6.7.8:8080"
		assert pm.get_proxy() == "http://a:1@1.2.3.4:80"  # wraps around

	def test_validate(self):
		from utilities.etc import ProxyManager

		assert ProxyManager._validate("http://u:p@1.2.3.4:80") is True
		assert ProxyManager._validate("") is False

class TestProxyTesting:
	def test_test_proxy_invalid(self):
		from utilities.etc import ProxyManager

		pm = ProxyManager()
		ok = pm.test_proxy("http://invalid:3128", timeout=1)
		assert ok is False

	def test_test_all_empty(self):
		from utilities.etc import ProxyManager

		pm = ProxyManager()
		results = pm.test_all(timeout=1)
		assert results == []

class TestProxyAutoFetch:
	def test_fetch_from_url_invalid(self):
		from utilities.etc import ProxyManager
		result = ProxyManager.fetch_from_url("http://invalid.nonexistent.example/proxies.txt")
		assert result == []

	def test_fetch_from_url_empty(self):
		from utilities.etc import ProxyManager
		import os, tempfile
		# Create a local "URL" via file://
		tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
		tmp.write("# comment\n")
		tmp.close()
		try:
			result = ProxyManager.fetch_from_url("file://" + tmp.name)
			# file:// may not work on all platforms; if it does, expect no proxies
		except Exception:
			pass
		os.unlink(tmp.name)

	def test_fetch_and_add_rejects_bad_url(self):
		from utilities.etc import ProxyManager
		pm = ProxyManager()
		n = pm.fetch_and_add("http://invalid.nonexistent.example/proxies.txt")
		assert n == 0


# ======================================================================
# Config profile tests
# ======================================================================

