"""Disk hygiene: Chromium profiles, stale files, backups, update leftovers.

Kept dependency-free (stdlib only) so ``utilities.etc`` can import it without
creating a cycle. Functions return ``(count, bytes)`` so callers decide how to
report results.
"""

import glob
import os
import shutil
import sys
import tempfile
import time

# Chromium profiles live outside the project directory: a crash or Ctrl+C used
# to leave 10-80 MB per worker behind in the current working directory.
PROFILE_ROOT = os.path.join(tempfile.gettempdir(), "MegaTemp")

BACKUP_DIR = os.path.join("credentials", "pruned")
DEFAULT_BACKUP_KEEP = 100


def profile_dir(name: str = "tmp") -> str:
	"""Return (and create) the profile directory for ``name``."""
	path = os.path.join(PROFILE_ROOT, name)
	os.makedirs(path, exist_ok=True)
	return path


def dir_size(path: str) -> tuple[int, int]:
	"""Return ``(file count, total bytes)`` for a file or directory."""
	if not os.path.exists(path):
		return 0, 0
	if os.path.isfile(path):
		try:
			return 1, os.path.getsize(path)
		except OSError:
			return 0, 0
	files = 0
	total = 0
	for root, _dirs, names in os.walk(path):
		for name in names:
			try:
				total += os.path.getsize(os.path.join(root, name))
				files += 1
			except OSError:
				continue
	return files, total


def cleanup_stale_profiles(
	max_age_hours: float = 24.0, root: str | None = None
) -> tuple[int, int]:
	"""Remove profile dirs under ``PROFILE_ROOT`` untouched for a day.

	Fresh profiles (another MegaTemp instance may be using them) and the root
	itself are never removed.
	"""
	base = root or PROFILE_ROOT
	if not os.path.isdir(base):
		return 0, 0
	cutoff = time.time() - max_age_hours * 3600
	removed = 0
	freed = 0
	for entry in os.listdir(base):
		path = os.path.join(base, entry)
		if not os.path.isdir(path):
			continue
		try:
			if os.path.getmtime(path) > cutoff:
				continue
		except OSError:
			continue
		files, size = dir_size(path)
		shutil.rmtree(path, ignore_errors=True)
		if not os.path.exists(path):
			removed += 1
			freed += size
		_ = files
	return removed, freed


def cleanup_orphan_parts(root: str = ".") -> tuple[int, int]:
	"""Delete leftover ``*.part`` downloads from interrupted runs."""
	count = 0
	freed = 0
	for path in glob.glob(os.path.join(root, "*.part")):
		try:
			size = os.path.getsize(path)
			os.remove(path)
			count += 1
			freed += size
		except OSError:
			continue
	return count, freed


def cleanup_update_leftovers() -> tuple[int, int]:
	"""Delete ``.old``/``.new`` files left by an interrupted auto-update."""
	count = 0
	freed = 0
	for suffix in (".old", ".new"):
		path = sys.executable + suffix
		try:
			size = os.path.getsize(path)
			os.remove(path)
			count += 1
			freed += size
		except OSError:
			continue
	return count, freed


def prune_backups(
	directory: str = BACKUP_DIR, keep: int = DEFAULT_BACKUP_KEEP
) -> tuple[int, int]:
	"""Keep only the ``keep`` newest files in the pruned-credentials backup dir."""
	if keep < 0 or not os.path.isdir(directory):
		return 0, 0
	entries = []
	for name in os.listdir(directory):
		path = os.path.join(directory, name)
		if not os.path.isfile(path):
			continue
		try:
			entries.append((os.path.getmtime(path), path))
		except OSError:
			continue
	entries.sort(reverse=True)
	removed = 0
	freed = 0
	for _mtime, path in entries[keep:]:
		try:
			size = os.path.getsize(path)
			os.remove(path)
			removed += 1
			freed += size
		except OSError:
			continue
	return removed, freed


def usage_report(root: str = ".") -> list[tuple[str, int, int]]:
	"""Return ``(label, file count, bytes)`` rows for the disk dashboard."""
	from utilities.fs import CREDENTIALS_DIR

	rows = [
		("Chromium profiles", *dir_size(PROFILE_ROOT)),
		("Credentials", *dir_size(CREDENTIALS_DIR)),
		("Pruned backups", *dir_size(BACKUP_DIR)),
	]
	parts = glob.glob(os.path.join(root, "*.part"))
	part_bytes = 0
	for path in parts:
		try:
			part_bytes += os.path.getsize(path)
		except OSError:
			continue
	rows.append(("Orphan .part files", len(parts), part_bytes))
	rows.append(("MegaTemp executable", *dir_size(sys.executable)))
	return rows


def clean_all(root: str = ".") -> list[tuple[str, int, int]]:
	"""Run every cleanup and return the ``(label, removed, bytes)`` results."""
	return [
		("Stale Chromium profiles", *cleanup_stale_profiles()),
		("Orphan .part files", *cleanup_orphan_parts(root)),
		("Update leftovers", *cleanup_update_leftovers()),
		("Old credential backups", *prune_backups()),
	]
