"""A small, dependency-free terminal UI (TUI) for MegaTemp.

Provides an interactive arrow-key driven menu. No external packages are used;
we drive a raw terminal directly with ANSI escape codes so it works in any
Linux terminal, tmux/screen session or SSH connection.

On Windows (where ``termios`` / ``tty`` are not available) the keyboard
reader falls back to ``msvcrt`` so the same menu works natively on all
platforms.
"""

import os
import sys
import select

from utilities import console
from utilities.etc import Colours, p_print

_WINDOWS = sys.platform == "win32"
if not _WINDOWS:
	import tty
	import termios
else:
	import msvcrt

# Arrow keys arrive as either normal-mode (\x1b[A) or application-cursor-mode
# (\x1bOA) sequences depending on the terminal; accept both.
UP = ("\x1b[A", "\x1bOA")
DOWN = ("\x1b[B", "\x1bOB")
LEFT = ("\x1b[D", "\x1bOD")
RIGHT = ("\x1b[C", "\x1bOC")
ENTER = "\r"
ESCAPE = "\x1b"

# Number keys 1-9 as jump shortcuts.
_DIGIT_KEYS = tuple(str(i) for i in range(1, 10))

# Box-drawing glyphs (all single-column in a Unicode terminal). When the
# terminal/encoding cannot render them (MEGATEMP_ASCII, TERM=dumb, legacy
# Windows code pages) we fall back to ASCII so the menu still renders.
_UNICODE_BOX = {
	"TL": "\u2554",
	"TR": "\u2557",
	"BL": "\u255a",
	"BR": "\u255d",
	"ML": "\u2551",
	"MR": "\u2551",
	"MLS": "\u2560",
	"MRS": "\u2563",
	"HBAR": "\u2550",
}
_ASCII_BOX = {
	"TL": "+",
	"TR": "+",
	"BL": "+",
	"BR": "+",
	"ML": "|",
	"MR": "|",
	"MLS": "+",
	"MRS": "+",
	"HBAR": "-",
}


def _box() -> dict[str, str]:
	return _UNICODE_BOX if console.unicode_ok() else _ASCII_BOX


TL, TR, BL, BR = (
	_UNICODE_BOX["TL"],
	_UNICODE_BOX["TR"],
	_UNICODE_BOX["BL"],
	_UNICODE_BOX["BR"],
)
ML, MR = _UNICODE_BOX["ML"], _UNICODE_BOX["MR"]
MLS, MRS = _UNICODE_BOX["MLS"], _UNICODE_BOX["MRS"]
HBAR = _UNICODE_BOX["HBAR"]

# Pointer shown next to the highlighted item. ASCII `>` is exactly one column
# wide everywhere, unlike arrows such as `\u25b8` which render as two columns
# in many terminals and would shift the right border out of alignment.
POINTER_ON = ">"
POINTER_OFF = " "


def _display_width(text: str) -> int:
	"""Visible column width of `text`.

	Counts the length of `text` ignoring ANSI colour escapes, and treats any
	non-ASCII character as two columns (a safe over-approximation that keeps
	the right border aligned even when wide glyphs sneak in).
	"""
	width = 0
	in_esc = False
	for ch in text:
		if ch == "\x1b":
			in_esc = True
			continue
		if in_esc:
			if ch == "m":
				in_esc = False
			continue
		width += 2 if ord(ch) > 0x2000 else 1
	return width


class MenuItem:
	"""A single selectable entry in a menu."""

	def __init__(self, label, callback=None, description="", value=None):
		self.label = label
		self.callback = callback
		self.description = description
		# `value` is shown at the right edge (e.g. a current setting). It may
		# be a string or a callable returning a string (so it stays live).
		self.value = value

	def get_value(self) -> str:
		if callable(self.value):
			try:
				return str(self.value())
			except Exception:
				return ""
		return str(self.value) if self.value is not None else ""


_BACK = object()


class Menu:
	"""An arrow-key navigable menu rendered with ANSI escape codes."""

	def __init__(
		self,
		title,
		items,
		subtitle=None,
		footer=None,
		width=52,
	):
		self.title = title
		self.items = items
		self.subtitle = subtitle
		if footer is None:
			footer = (
				"Use \u2191\u2193 arrows \u2022 Enter to select \u2022 q to go back"
				if console.unicode_ok()
				else "Use Up/Down arrows, Enter to select, q to go back"
			)
		self.footer = footer
		self.width = width
		self.selected = 0
		self._drawn_lines = 0
		# When True the next render does a full screen clear (used on first
		# paint and after an action returns), otherwise it updates in place.
		self._full_redraw = True

	@staticmethod
	def _get_key():
		"""Read a single key press.

		On Unix uses raw ``os.read`` on the terminal fd so escape sequences
		are captured byte-accurately. Arrow keys arrive as a 3-byte sequence
		starting with ``\\x1b`` (either ``\\x1b[A``/``\\x1b[B`` in normal
		mode or ``\\x1bOA``/``\\x1bOB`` in application-cursor mode); a lone
		``\\x1b`` with no following bytes within a short window is treated as
		Esc.

		On Windows falls back to ``msvcrt.getwch()`` and maps the extended
		arrow codes back to the same escape sequences the Unix path produces.
		"""
		if _WINDOWS:
			first = msvcrt.getwch()
			if first == "\xe0":  # Extended key (arrows, etc.)
				second = msvcrt.getwch()
				mapping = {"H": UP[0], "P": DOWN[0], "K": LEFT[0], "M": RIGHT[0]}
				return mapping.get(second, ESCAPE)
			if first == "\x1b":
				# Check if next char is available immediately
				if msvcrt.kbhit():
					return ESCAPE  # treat lone Esc as escape
				return ESCAPE
			if first == "\r":
				return ENTER
			return first
		fd = sys.stdin.fileno()
		old = termios.tcgetattr(fd)
		try:
			tty.setraw(fd)
			first = os.read(fd, 1)
			if first != b"\x1b":
				return first.decode("utf-8", "replace")
			# Could be an arrow sequence or a standalone Escape key.
			ready, _, _ = select.select([fd], [], [], 0.3)
			if not ready:
				return ESCAPE
			rest = b""
			while len(rest) < 2:
				chunk = os.read(fd, 2 - len(rest))
				if not chunk:
					break
				rest += chunk
			return (b"\x1b" + rest).decode("utf-8", "replace")
		finally:
			termios.tcsetattr(fd, termios.TCSADRAIN, old)

	def _render(self):
		if self._full_redraw:
			# Move to the top-left and clear everything for a clean slate.
			sys.stdout.write("\x1b[2J\x1b[H")
			self._drawn_lines = 0
		elif self._drawn_lines:
			# Jump back up over the previous frame and clear downwards.
			sys.stdout.write(f"\x1b[{self._drawn_lines}A\x1b[J")

		w = self.width
		box = _box()
		tl, tr, bl, br = box["TL"], box["TR"], box["BL"], box["BR"]
		ml, mr = box["ML"], box["MR"]
		mls, mrs, hbar = box["MLS"], box["MRS"], box["HBAR"]
		lines = []
		lines.append(f"{tl}{hbar * (w + 2)}{tr}")
		lines.append(f"{ml} {self.title.center(w)} {mr}")
		lines.append(f"{mls}{hbar * (w + 2)}{mrs}")
		if self.subtitle:
			lines.append(f"{ml} {self.subtitle.ljust(w)} {mr}")
			lines.append(f"{mls}{hbar * (w + 2)}{mrs}")

		for idx, item in enumerate(self.items):
			pointer = POINTER_ON if idx == self.selected else POINTER_OFF
			label = item.label
			value = item.get_value()
			if value:
				gap = (
					w
					- _display_width(pointer)
					- _display_width(label)
					- _display_width(value)
					- 1
				)
				if gap < 1:
					gap = 1
				row = f"{pointer}{label}{' ' * gap}{value}"
			else:
				row = f"{pointer}{label}"
			if idx == self.selected:
				row = f"{Colours.OKGREEN}{row}{Colours.ENDC}"
			# Pad by visible width so the right border stays aligned.
			pad = w - _display_width(row)
			if pad < 0:
				pad = 0
			row = f"{row}{' ' * pad}"
			lines.append(f"{ml} {row} {mr}")

		lines.append(f"{mls}{hbar * (w + 2)}{mrs}")
		desc = self.items[self.selected].description
		foot = desc if desc else (self.footer or "")
		lines.append(f"{ml} {foot.ljust(w)} {mr}")
		lines.append(f"{bl}{hbar * (w + 2)}{br}")

		sys.stdout.write("\n".join(lines) + "\n")
		sys.stdout.flush()
		self._drawn_lines = len(lines)
		self._full_redraw = False

	def run(self) -> object | None:
		"""Run the menu loop; returns the selected callback's result.

		Raises ``RuntimeError`` when stdin is not a terminal, so callers can
		fall back to a non-interactive mode instead of hanging on input.
		"""
		if not (sys.stdin and sys.stdin.isatty()):
			raise RuntimeError(
				"Interactive menu requires a terminal (stdin is not a TTY). "
				"Use CLI flags (e.g. --health, --loop, --keepalive) instead."
			)
		self._full_redraw = True
		sys.stdout.write("\x1b[?25l")  # hide cursor while redrawing
		try:
			while True:
				self._render()
				key = self._get_key()
				if key in UP:
					self.selected = (self.selected - 1) % len(self.items)
					self._full_redraw = False
				elif key in DOWN:
					self.selected = (self.selected + 1) % len(self.items)
					self._full_redraw = False
				elif key in _DIGIT_KEYS:
					idx = int(key) - 1
					if 0 <= idx < len(self.items):
						self.selected = idx
					self._full_redraw = False
				elif key in (ENTER, *RIGHT):
					item = self.items[self.selected]
					if item.callback is None:
						continue
					try:
						result = item.callback()
					finally:
						# Always force a full repaint on the next loop iteration,
						# even if the callback raised an exception.
						self._full_redraw = True
					if result is _BACK:
						return _BACK
				elif key in ("q", "Q", ESCAPE):
					return _BACK
				elif key == "\x03":  # Ctrl+C
					return _BACK
		finally:
			# Always restore the cursor and colours, even if a callback raised.
			sys.stdout.write("\x1b[?25h" + Colours.ENDC + "\n")
			sys.stdout.flush()


def prompt_text(message: str, default: str = "") -> str:
	"""Ask the user for a line of text (releases raw mode first)."""
	sys.stdout.write("\x1b[2K")
	msg = message + (f" [{default}]" if default else "")
	sys.stdout.write(msg + ": ")
	sys.stdout.flush()
	try:
		val = input()
	except EOFError:
		val = ""
	if val == "" and default != "":
		return default
	return val


def _path_completer(text, state):
	"""Readline completer for file paths."""
	import glob as _glob

	matches = _glob.glob(text + "*") or [text]
	matches.sort()
	try:
		return matches[state]
	except IndexError:
		return None


def prompt_path(message: str, default: str = "", must_exist: bool = False) -> str:
	"""Ask for a file path with Tab completion (releases raw mode)."""
	sys.stdout.write("\x1b[2K")
	msg = message + (f" [{default}]" if default else "")
	sys.stdout.write(msg + ": ")
	sys.stdout.flush()
	try:
		import readline as _rl

		_rl.set_completer(_path_completer)
		_rl.parse_and_bind("tab: complete")
		_rl.set_completer_delims(" \t\n;")
		val = input()
	except ImportError:
		# readline not available (Windows) — fall back to plain input
		try:
			val = input()
		except EOFError:
			val = ""
	except EOFError:
		val = ""
	if val == "" and default != "":
		val = default
	if must_exist and val and not os.path.exists(os.path.expanduser(val)):
		p_print(f"Path not found: {val}", Colours.FAIL)
		return prompt_path(message, default, must_exist)
	return val


def prompt_int(
	message: str, default: int = 1, minimum: int = 1, maximum: int = 100000
) -> int:
	"""Ask for an integer within a range."""
	while True:
		raw = prompt_text(message, str(default))
		try:
			val = int(raw)
		except ValueError:
			p_print("Please enter a valid number.", Colours.WARNING)
			continue
		if val < minimum or val > maximum:
			p_print(
				f"Please enter a value between {minimum} and {maximum}.",
				Colours.WARNING,
			)
			continue
		return val


def prompt_yes_no(message: str, default_no: bool = True) -> bool:
	"""Yes/No prompt returning a bool."""
	suffix = " [y/N]" if default_no else " [Y/n]"
	while True:
		raw = prompt_text(message + suffix).strip().lower()
		if raw == "":
			return not default_no
		if raw in ("y", "yes"):
			return True
		if raw in ("n", "no"):
			return False
		p_print("Please answer y or n.", Colours.WARNING)


def pause(message: str = "Press Enter to return to the menu...") -> None:
	"""Pause with a message, releasing raw mode for input()."""
	sys.stdout.write("\x1b[2K" + message)
	sys.stdout.flush()
	try:
		input()
	except EOFError:
		pass
