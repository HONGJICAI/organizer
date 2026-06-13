import asyncio


# ---------------------------------------------------------------------------
# Backup task tests
# ---------------------------------------------------------------------------

class TestBackupDatabase:
    def test_no_db_file(self, tmp_path, monkeypatch):
        from tasks.backup import backup_database
        monkeypatch.chdir(tmp_path)
        asyncio.run(backup_database())
        assert not (tmp_path / "dbbackup").exists()

    def test_creates_backup(self, tmp_path, monkeypatch):
        from tasks.backup import backup_database
        monkeypatch.chdir(tmp_path)
        (tmp_path / "prod.sqlite").write_bytes(b"db content")
        asyncio.run(backup_database())
        backups = list((tmp_path / "backups").glob("prod_*.sqlite"))
        assert len(backups) == 1

    def test_skips_when_unchanged(self, tmp_path, monkeypatch):
        from tasks.backup import backup_database
        monkeypatch.chdir(tmp_path)
        (tmp_path / "prod.sqlite").write_bytes(b"db content")
        asyncio.run(backup_database())
        asyncio.run(backup_database())
        # shutil.copy2 preserves mtime, so second run should be skipped
        backups = list((tmp_path / "backups").glob("prod_*.sqlite"))
        assert len(backups) == 1

    def test_prunes_old_backups(self, tmp_path, monkeypatch):
        import os
        import time
        from tasks.backup import backup_database
        monkeypatch.chdir(tmp_path)
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()
        old_mtime = time.time() - 3600
        for i in range(8):
            f = backup_dir / f"prod_20200101_00000{i}.sqlite"
            f.write_bytes(b"old")
            os.utime(f, (old_mtime, old_mtime))
        (tmp_path / "prod.sqlite").write_bytes(b"new content")
        asyncio.run(backup_database())
        backups = list(backup_dir.glob("prod_*.sqlite"))
        assert len(backups) == 7

    def test_keeps_at_most_seven(self, tmp_path, monkeypatch):
        import os
        import time
        from tasks.backup import backup_database
        monkeypatch.chdir(tmp_path)
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()
        old_mtime = time.time() - 3600
        for i in range(10):
            f = backup_dir / f"prod_20200101_0000{i:02d}.sqlite"
            f.write_bytes(b"old")
            os.utime(f, (old_mtime, old_mtime))
        (tmp_path / "prod.sqlite").write_bytes(b"content")
        asyncio.run(backup_database())
        backups = list(backup_dir.glob("prod_*.sqlite"))
        assert len(backups) == 7
