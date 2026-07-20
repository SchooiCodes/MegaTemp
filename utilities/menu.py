"""A small, dependency-free terminal UI (TUI) for MegaTemp.

Provides an interactive arrow-key driven menu. No external packages are used;
we drive a raw terminal directly with ANSI escape codes so it works in any
Linux terminal, tmux/screen session or SSH connection.
"""

import sys
import tty
import termios

from utilities.etc import Colours, p_print

UP = "\x1b[A"
DOWN = "\x1b[B"
LEFT = "\x1b[D"
RIGHT = "\x1b[C"
ENTER = "\r"
ESCAPE = "\x1b"


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
		footer="Use \u2191\u2193 arrows \u2022 Enter to select \u2022 q/Esc to go back",
		width=52,
	):
		self.title = title
		self.items = items
		self.subtitle = subtitle
		self.footer = footer
		self.width = width
		self.selected = 0
		self._drawn_lines = 0

	@staticmethod
	def _get_key():
		"""Read a single key (handles escape sequences for arrows)."""
		fd = sys.stdin.fileno()
		old = termios.tcgetattr(fd)
		try:
			tty.setraw(fd)
			ch = sys.stdin.read(1)
			if ch == ESCAPE:
				seq = sys.stdin.read(2)
				return ESCAPE + seq
			return ch
		finally:
			termios.tcsetattr(fd, termios.TCSADRAIN, old)

	def _bar(self, ch="\u2500"):
		return ch * (self.width + 2)

	def _render(self):
		if self._drawn_lines:
			sys.stdout.write(f"\x1b[{self._drawn_lines}A")
		sys.stdout.write("\x1b[J")

		tl, hbar, tr = "\u2554", "\u2550", "\u2557"
		ml, mr = "\u2551", "\u2551"
		mls, mrs = "\u2560", "\u2563"
		bl, br = "\u255a", "\u255d"

		w = self.width
		lines = []
		lines.append(f"{tl}{self._bar(hbar)}{tr}")
		lines.append(f"{ml} {self.title.center(w)} {mr}")
		lines.append(f"{mls}{self._bar(hbar)}{mrs}")
		if self.subtitle:
			lines.append(f"{ml} {self.subtitle.ljust(w)} {mr}")
			lines.append(f"{mls}{self._bar(hbar)}{mrs}")

		for idx, item in enumerate(self.items):
			pointer = "\u25b8 " if idx == self.selected else "  "
			label = item.label
			value = item.get_value()
			if value:
				gap = w - len(label) - len(value) - 1
				if gap < 1:
					gap = 1
				row = f"{pointer}{label}{' ' * gap}{value}"
			else:
				row = f"{pointer}{label}"
			if idx == self.selected:
				row = f"{Colours.OKGREEN}{row}{Colours.ENDC}"
			lines.append(f"{ml} {row.ljust(w)} {mr}")

		lines.append(f"{mls}{self._bar(hbar)}{mrs}")
		desc = self.items[self.selected].description
		foot = desc if desc else (self.footer or "")
		lines.append(f"{ml} {foot.ljust(w)} {mr}")
		lines.append(f"{bl}{self._bar(hbar)}{br}")

		sys.stdout.write("\n".join(lines) + "\n")
		sys.stdout.flush()
		self._drawn_lines = len(lines)

	def run(self):
		"""Run the menu loop; returns the selected callback's result."""
		self._drawn_lines = 0
		while True:
			self._render()
			key = self._get_key()
			if key == UP:
				self.selected = (self.selected - 1) % len(self.items)
			elif key == DOWN:
				self.selected = (self.selected + 1) % len(self.items)
			elif key in (ENTER, RIGHT):
				item = self.items[self.selected]
				if item.callback is None:
					continue
				return item.callback()
			elif key in ("q", "Q") or key == ESCAPE + "[":
				return _BACK


def prompt_text(message, default=""):
	"""Ask the user for a line of text (releases raw mode first)."""
	fd = sys.stdin.fileno()
	try:
		termios.tcsetattr(fd, termios.TCSADRAIN, termios.tcgetattr(fd))
	except Exception:
		pass
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
