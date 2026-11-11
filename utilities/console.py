"""Console/stdio helpers: encoding safety, colour and Unicode detection.

Imported as early as possible (before anything prints) so that redirected or
piped output can never raise ``UnicodeEncodeError`` on Windows' legacy code
pages, and so that colour/box-drawing glyphs are only used when the terminal
can render them.

Environment variables:

* ``NO_COLOR`` / ``CLICOLOR=0`` — disable ANSI colour.
* ``FORCE_COLOR`` — enable ANSI colour even when not a TTY.
* ``MEGATEMP_ASCII=1`` — force ASCII-only output (no box drawing/emoji).
"""

import os
import sys

_unicode = True
_colour = True
_initialised = False

_UTF8_NAMES = ("utf8", "utf16", "utf32")
_COLOUR_FIELDS = ("HEADER", "OKBLUE", "OKCYAN", "OKGREEN", "WARNING", "FAIL", "ENDC")


def _normalise_encoding(name: str) -> str:
	return (name or "").lower().replace("-", "").replace("_", "")


def _is_utf8(stream) -> bool:
	enc = _normalise_encoding(getattr(stream, "encoding", ""))
	return enc == "" or enc in _UTF8_NAMES


def _stream_supports_colour(stream) -> bool:
	if os.environ.get("NO_COLOR"):
		return False
	if os.environ.get("CLICOLOR") == "0":
		return False
	if os.environ.get("TERM", "") == "dumb":
		return False
	if os.environ.get("FORCE_COLOR"):
		return True
	try:
		return bool(stream.isatty())
	except (AttributeError, ValueError, OSError):
		return False


def init() -> bool:
	"""Make stdio total and configure colour/Unicode output.

	Returns ``True`` when Unicode glyphs are safe to print. Safe to call more
	than once; later calls only re-evaluate the environment.
	"""
	global _unicode, _colour, _initialised

	_unicode = True
	for stream in (sys.stdout, sys.stderr):
		if not _is_utf8(stream):
			try:
				stream.reconfigure(encoding="utf-8", errors="replace")
			except (AttributeError, ValueError, OSError):
				_unicode = False
	if not _is_utf8(sys.stdout):
		_unicode = False
	if os.environ.get("MEGATEMP_ASCII") or os.environ.get("TERM") == "dumb":
		_unicode = False

	_colour = _stream_supports_colour(sys.stdout)
	if not _colour:
		from utilities.models import Colours

		for field in _COLOUR_FIELDS:
			setattr(Colours, field, "")
	_initialised = True
	return _unicode


def unicode_ok() -> bool:
	"""True when box-drawing/emoji glyphs can be written safely."""
	return _unicode


def colour_enabled() -> bool:
	"""True when ANSI colour should be emitted."""
	return _colour


def initialised() -> bool:
	return _initialised
