"""Report where MegaTemp and its build artifacts use disk space.

Run: python scripts/disk_report.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utilities import console  # noqa: E402

console.init()

from utilities.disk import dir_size, usage_report  # noqa: E402


def _mb(size: int) -> str:
	return f"{size / 1048576:.1f} MB"


def main() -> int:
	root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
	print("Runtime")
	for label, count, size in usage_report(root):
		print(f"  {label:<24} {count:>5} files  {_mb(size):>9}")
	print("\nBuild artifacts")
	for name in ("dist", "build"):
		count, size = dir_size(os.path.join(root, name))
		print(f"  {name:<24} {count:>5} files  {_mb(size):>9}")
	count, size = dir_size(root)
	print(f"  {'repo total':<24} {count:>5} files  {_mb(size):>9}")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
