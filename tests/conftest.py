import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Patch asyncio.coroutine before any module imports tenacity's async retry
# (removed in Python 3.11+). main.py does the same at startup.
import utilities.compat  # noqa: E402,F401

import pytest


@pytest.fixture
def isolated_fs(tmp_path):
    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    yield tmp_path
    os.chdir(old_cwd)
