"""A small, dependency-free terminal UI (TUI) for MegaTemp.

Provides an interactive arrow-key driven menu. No external packages are used;
we drive a raw terminal directly with ANSI escape codes so it works in any
Linux terminal, tmux/screen session or SSH connection.
"""

import sys
import tty
import termios
import select

from utilities.etc import Colours, p_print

UP = "\x1b[A"
DOWN = "\x1b[B"
LEFT = "\x1b[D"
RIGHT = "\x1b[C"
ENTER = "\r"
ESCAPE = "\x1b"

# Box-drawing glyphs (all single-column in a Unicode terminal).
TL, TR, BL, BR = "\u2554", "\u2557", "\u255a", "\u255d"
ML, MR = "\u2551", "\u2551"
MLS, MRS = "\u2560", "\u2563"
HBAR = "\u2550"

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

	def get_value(self):
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
		footer="Use \u2191\u2193 arrows \u2022 Enter to select \u2022 q to go back",
		width=52,
	):
		self.title = title
		self.items = items
		self.subtitle = subtitle
		self.footer = footer
		self.width = width
		self.selected = 0
		self._drawn_lines = 0
		# When True the next render does a full screen clear (used on first
		# paint and after an action returns), otherwise it updates in place.
		self._full_redraw = True

	@staticmethod
	def _read_escape() -> str:
		"""Read an arrow/escape sequence without blocking on a lone Esc."""
		# After the initial \x1b, only consume more bytes if they arrive
		# promptly; otherwise treat the key as a standalone Escape.
		ready, _, _ = select.select([sys.stdin], [], [], 0.15)
		if not ready:
			return ESCAPE
		seq = sys.stdin.read(2)
		return ESCAPE + seq

	def _get_key(self):
		"""Read a single key (handles escape sequences for arrows)."""
		fd = sys.stdin.fileno()
		old = termios.tcgetattr(fd)
		try:
			tty.setraw(fd)
			ch = sys.stdin.read(1)
			if ch == ESCAPE:
				return self._read_escape()
			return ch
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
		lines = []
		lines.append(f"{TL}{HBAR * (w + 2)}{TR}")
		lines.append(f"{ML} {self.title.center(w)} {MR}")
		lines.append(f"{MLS}{HBAR * (w + 2)}{MRS}")
		if self.subtitle:
			lines.append(f"{ML} {self.subtitle.ljust(w)} {MR}")
			lines.append(f"{MLS}{HBAR * (w + 2)}{MRS}")

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
			lines.append(f"{ML} {row} {MR}")

		lines.append(f"{MLS}{HBAR * (w + 2)}{MRS}")
		desc = self.items[self.selected].description
		foot = desc if desc else (self.footer or "")
		lines.append(f"{ML} {foot.ljust(w)} {MR}")
		lines.append(f"{BL}{HBAR * (w + 2)}{BR}")

		sys.stdout.write("\n".join(lines) + "\n")
		sys.stdout.flush()
		self._drawn_lines = len(lines)
		self._full_redraw = False

	def run(self):
		"""Run the menu loop; returns the selected callback's result."""
		self._full_redraw = True
		while True:
			self._render()
			key = self._get_key()
			if key == UP:
				self.selected = (self.selected - 1) % len(self.items)
				self._full_redraw = False
			elif key == DOWN:
				self.selected = (self.selected + 1) % len(self.items)
				self._full_redraw = False
			elif key in (ENTER, RIGHT):
				item = self.items[self.selected]
				if item.callback is None:
					continue
				result = item.callback()
				# Any action prints logs then returns here; force a clean
				# full repaint of the menu on the next loop iteration.
				self._full_redraw = True
				if result is _BACK:
					return _BACK
			elif key in ("q", "Q", ESCAPE):
				return _BACK


def prompt_text(message, default=""):
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


def prompt_int(message, default=1, minimum=1, maximum=100000):
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


def prompt_yes_no(message, default_no=True):
	"""Yes/No prompt returning a bool."""
	suffix = " [y/N]: " if default_no else " [Y/n]: "
	while True:
		raw = prompt_text(message + suffix).strip().lower()
		if raw == "":
			return not default_no
		if raw in ("y", "yes"):
			return True
		if raw in ("n", "no"):
			return False
		p_print("Please answer y or n.", Colours.WARNING)


def pause(message="Press Enter to return to the menu..."):
	"""Pause with a message, releasing raw mode for input()."""
	prompt_text(message)
