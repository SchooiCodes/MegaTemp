import os
import time

from utilities import disk


def test_profile_dir_created(tmp_path, monkeypatch):
	monkeypatch.setattr(disk, "PROFILE_ROOT", str(tmp_path / "profiles"))
	path = disk.profile_dir("tmp_1")
	assert os.path.isdir(path)
	assert path.endswith(os.path.join("profiles", "tmp_1"))


def test_stale_profiles_removed_fresh_kept(tmp_path, monkeypatch):
	monkeypatch.setattr(disk, "PROFILE_ROOT", str(tmp_path))
	old = tmp_path / "tmp_0"
	old.mkdir()
	(old / "data").write_bytes(b"0" * 100)
	fresh = tmp_path / "tmp_1"
	fresh.mkdir()
	stamp = time.time() - 48 * 3600
	os.utime(old, (stamp, stamp))

	removed, freed = disk.cleanup_stale_profiles()

	assert removed == 1
	assert freed >= 100
	assert not old.exists()
	assert fresh.exists()


def test_orphan_parts_and_update_leftovers(tmp_path, monkeypatch):
	(tmp_path / "movie.mp4.part").write_bytes(b"x" * 10)
	assert disk.cleanup_orphan_parts(str(tmp_path)) == (1, 10)
	assert not (tmp_path / "movie.mp4.part").exists()

	fake_exe = tmp_path / "MegaTemp.exe"
	fake_exe.write_bytes(b"x")
	monkeypatch.setattr(disk.sys, "executable", str(fake_exe))
	(tmp_path / "MegaTemp.exe.old").write_bytes(b"y" * 5)
	(tmp_path / "MegaTemp.exe.new").write_bytes(b"z" * 5)

	assert disk.cleanup_update_leftovers() == (2, 10)


def test_prune_backups_keeps_newest(tmp_path):
	for i in range(5):
		path = tmp_path / f"f{i}.json"
		path.write_text("x", encoding="utf-8")
		os.utime(path, (1000 + i, 1000 + i))

	removed, _freed = disk.prune_backups(str(tmp_path), keep=2)

	assert removed == 3
	assert sorted(p.name for p in tmp_path.iterdir()) == ["f3.json", "f4.json"]


def test_clean_all_reports_every_stage(tmp_path, monkeypatch):
	monkeypatch.setattr(disk, "PROFILE_ROOT", str(tmp_path / "profiles"))
	monkeypatch.setattr(disk, "BACKUP_DIR", str(tmp_path / "pruned"))

	rows = disk.clean_all(str(tmp_path))

	assert len(rows) == 4
	assert all(len(row) == 3 for row in rows)
