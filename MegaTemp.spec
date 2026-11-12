# -*- mode: python ; coding: utf-8 -*-
import sys

from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = [
	'pymailtm',
	'pymailtm.pymailtm',
	'pyppeteer',
	'mega',
	'psutil',
	'requests',
]
tmp_ret = collect_all('pyppeteer')
datas += tmp_ret[0]
binaries += tmp_ret[1]
hiddenimports += tmp_ret[2]
tmp_ret = collect_all('pymailtm')
datas += tmp_ret[0]
binaries += tmp_ret[1]
hiddenimports += tmp_ret[2]
tmp_ret = collect_all('mega')
datas += tmp_ret[0]
binaries += tmp_ret[1]
hiddenimports += tmp_ret[2]

# Keep the one-file binary small: these are never imported by MegaTemp and
# PyInstaller would otherwise pull them in through transitive imports.
excludes = [
	'tkinter',
	'_tkinter',
	'pytest',
	'_pytest',
	'setuptools',
	'pip',
	'wheel',
	'IPython',
	'numpy',
	'PIL',
	'matplotlib',
	'pandas',
	'pydoc',
	'doctest',
]

a = Analysis(
	['main.py'],
	pathex=[],
	binaries=binaries,
	datas=datas,
	hiddenimports=hiddenimports,
	hookspath=[],
	hooksconfig={},
	runtime_hooks=[],
	excludes=excludes,
	noarchive=False,
	# 2 = drop docstrings/asserts from bundled modules.
	optimize=2,
)
pyz = PYZ(a.pure)

exe = EXE(
	pyz,
	a.scripts,
	a.binaries,
	a.datas,
	[],
	name='MegaTemp',
	debug=False,
	bootloader_ignore_signals=False,
	# `strip` needs GNU binutils, which is absent on Windows runners.
	strip=sys.platform != 'win32',
	upx=True,
	upx_exclude=[],
	runtime_tmpdir=None,
	console=True,
	disable_windowed_traceback=False,
	argv_emulation=False,
	target_arch=None,
	codesign_identity=None,
	entitlements_file=None,
)
