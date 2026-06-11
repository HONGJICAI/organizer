import asyncio
from datetime import datetime

from sqlmodel import Session, select

from model import ComicEntity
from tasks.cleanup import cleanup_missing_comics


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


# ---------------------------------------------------------------------------
# Cleanup task tests
# ---------------------------------------------------------------------------

class TestCleanupMissingComics:
    def test_empty_db(self, task_engine):
        asyncio.run(cleanup_missing_comics())

    def test_keeps_existing_file(self, task_session, task_engine, tmp_path):
        f = tmp_path / "present.zip"
        f.write_bytes(b"data")
        comic = ComicEntity(
            id=1, name="present.zip", path=str(f),
            size=100, updateTime=datetime.now(), page=1,
        )
        task_session.add(comic)
        task_session.commit()

        asyncio.run(cleanup_missing_comics())

        with Session(task_engine) as s:
            assert s.get(ComicEntity, 1) is not None

    def test_removes_missing_file(self, task_session, task_engine):
        comic = ComicEntity(
            id=2, name="gone.zip", path="/nonexistent/gone.zip",
            size=100, updateTime=datetime.now(), page=1,
        )
        task_session.add(comic)
        task_session.commit()

        asyncio.run(cleanup_missing_comics())

        with Session(task_engine) as s:
            assert s.get(ComicEntity, 2) is None

    def test_skips_archived_even_if_missing(self, task_session, task_engine):
        comic = ComicEntity(
            id=3, name="archived.zip", path="/nonexistent/archived.zip",
            size=100, updateTime=datetime.now(), page=1, archived=True,
        )
        task_session.add(comic)
        task_session.commit()

        asyncio.run(cleanup_missing_comics())

        with Session(task_engine) as s:
            assert s.get(ComicEntity, 3) is not None

    def test_removes_multiple_missing(self, task_session, task_engine):
        for i in range(1, 4):
            comic = ComicEntity(
                id=i, name=f"missing{i}.zip", path=f"/gone/{i}.zip",
                size=100, updateTime=datetime.now(), page=1,
            )
            task_session.add(comic)
        task_session.commit()

        asyncio.run(cleanup_missing_comics())

        with Session(task_engine) as s:
            remaining = s.exec(select(ComicEntity)).all()
            assert len(remaining) == 0
