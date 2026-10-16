import asyncio


# ---------------------------------------------------------------------------
# Backup task tests
# ---------------------------------------------------------------------------

def make_db(path, rows=1):
    import sqlite3
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE IF NOT EXISTS t (v INTEGER)")
    conn.executemany("INSERT INTO t VALUES (?)", [(i,) for i in range(rows)])
    conn.commit()
    conn.close()


def count_rows(path):
    import sqlite3
    conn = sqlite3.connect(path)
    try:
        return conn.execute("SELECT COUNT(*) FROM t").fetchone()[0]
    finally:
        conn.close()


class TestBackupDatabase:
    def test_no_db_file(self, tmp_path, monkeypatch):
        from tasks.backup import backup_database
        monkeypatch.chdir(tmp_path)
        asyncio.run(backup_database())
        assert not (tmp_path / "backups").exists()

    def test_creates_usable_backup(self, tmp_path, monkeypatch):
        from tasks.backup import backup_database
        monkeypatch.chdir(tmp_path)
        make_db(tmp_path / "prod.sqlite", rows=3)
        asyncio.run(backup_database())
        [backup] = list((tmp_path / "backups").glob("prod_*.sqlite"))
        assert count_rows(backup) == 3

    def test_skips_when_unchanged(self, tmp_path, monkeypatch):
        from tasks.backup import backup_database
        monkeypatch.chdir(tmp_path)
        make_db(tmp_path / "prod.sqlite")
        asyncio.run(backup_database())
        asyncio.run(backup_database())
        backups = list((tmp_path / "backups").glob("prod_*.sqlite"))
        assert len(backups) == 1

    def test_backs_up_again_after_a_change(self, tmp_path, monkeypatch):
        import os
        import time
        from tasks.backup import backup_database
        monkeypatch.chdir(tmp_path)
        db = tmp_path / "prod.sqlite"
        make_db(db)
        asyncio.run(backup_database())
        [first] = list((tmp_path / "backups").glob("prod_*.sqlite"))
        # Backups are named by the second; make the next one sort after.
        os.rename(first, first.with_name("prod_20000101_000000.sqlite"))
        os.utime(first.with_name("prod_20000101_000000.sqlite"), (time.time() - 60,) * 2)
        make_db(db, rows=2)
        asyncio.run(backup_database())
        backups = sorted((tmp_path / "backups").glob("prod_*.sqlite"))
        assert len(backups) == 2
        assert count_rows(backups[-1]) == 3

    def test_snapshot_ignores_uncommitted_writes(self, tmp_path, monkeypatch):
        import sqlite3
        from tasks.backup import backup_database
        monkeypatch.chdir(tmp_path)
        db = tmp_path / "prod.sqlite"
        make_db(db, rows=2)
        writer = sqlite3.connect(db)
        writer.execute("BEGIN")
        writer.execute("INSERT INTO t VALUES (99)")
        try:
            asyncio.run(backup_database())
        finally:
            writer.rollback()
            writer.close()
        [backup] = list((tmp_path / "backups").glob("prod_*.sqlite"))
        assert count_rows(backup) == 2

    def test_failed_backup_leaves_no_file(self, tmp_path, monkeypatch):
        from tasks.backup import backup_database
        monkeypatch.chdir(tmp_path)
        (tmp_path / "prod.sqlite").write_bytes(b"not a database" * 100)
        asyncio.run(backup_database())
        assert list((tmp_path / "backups").glob("prod_*.sqlite")) == []

    def test_runs_off_the_event_loop(self, tmp_path, monkeypatch):
        import threading
        import tasks.backup as backup
        monkeypatch.chdir(tmp_path)
        make_db(tmp_path / "prod.sqlite")
        seen = []
        monkeypatch.setattr(backup, "_sqlite_backup", lambda src, dst: seen.append(threading.current_thread()))
        asyncio.run(backup.backup_database())
        assert seen and seen[0] is not threading.main_thread()

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
        make_db(tmp_path / "prod.sqlite")
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
        make_db(tmp_path / "prod.sqlite")
        asyncio.run(backup_database())
        backups = list(backup_dir.glob("prod_*.sqlite"))
        assert len(backups) == 7