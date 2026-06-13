"""Tests for smaller coverage gaps: openapi, db, exception handlers, error paths."""
import asyncio
from unittest.mock import patch


from conftest import insert_comic


# ---------------------------------------------------------------------------
# db.get_session — the generator body needs direct exercise
# ---------------------------------------------------------------------------

def test_get_session_yields_session():
    from sqlmodel import Session
    import db
    gen = db.get_session()
    session = next(gen)
    assert isinstance(session, Session)
    try:
        next(gen)
    except StopIteration:
        pass


def test_ensure_column_adds_and_is_idempotent(monkeypatch):
    """The hand-rolled migration must add a missing column to an existing
    table (SQLModel.create_all never ALTERs) and be safe to run repeatedly."""
    from sqlalchemy import create_engine as sa_create_engine
    import db

    eng = sa_create_engine("sqlite://")
    with eng.connect() as conn:
        conn.exec_driver_sql("CREATE TABLE t (id INTEGER PRIMARY KEY)")
        conn.commit()
    monkeypatch.setattr(db, "engine", eng)

    def cols():
        with eng.connect() as conn:
            return {r[1] for r in conn.exec_driver_sql("PRAGMA table_info(t)")}

    assert "flag" not in cols()
    db._ensure_column("t", "flag", "flag BOOLEAN NOT NULL DEFAULT 0")
    assert "flag" in cols()
    # second run is a no-op, not an error
    db._ensure_column("t", "flag", "flag BOOLEAN NOT NULL DEFAULT 0")
    assert "flag" in cols()


# ---------------------------------------------------------------------------
# core/openapi.py — custom_openapi_schema
# ---------------------------------------------------------------------------

def test_custom_openapi_schema(client):
    r = client.get("/api/openapi.json")
    assert r.status_code == 200
    schema = r.json()
    assert "paths" in schema
    # Operation IDs should be deduped (no collisions)
    op_ids = [
        op.get("operationId")
        for path in schema["paths"].values()
        for op in path.values()
        if isinstance(op, dict) and "operationId" in op
    ]
    assert len(op_ids) == len(set(op_ids))


# ---------------------------------------------------------------------------
# core/exceptions.py — validation error handler (400 with pydantic errors)
# ---------------------------------------------------------------------------

def test_validation_error_returns_400(client):
    # Sending a non-integer id triggers FastAPI request validation
    r = client.get("/api/comics/not-an-int")
    assert r.status_code == 422 or r.status_code == 400


def test_validation_error_on_bad_body(client, session):
    insert_comic(session, 1)
    # name field is required; sending empty body triggers validation
    r = client.post("/api/comics/1/rename", content=b"not json",
                    headers={"content-type": "application/json"})
    assert r.status_code == 400 or r.status_code == 422


# ---------------------------------------------------------------------------
# api/comics.py — delete 500 error path (unexpected file system error)
# ---------------------------------------------------------------------------

def test_delete_unexpected_error_returns_500(client, session, tmp_path):
    from conftest import make_zip_comic
    f = tmp_path / "err.zip"
    make_zip_comic(str(f))
    insert_comic(session, 1, path=str(f))
    with patch("shutil.rmtree", side_effect=PermissionError("denied")), \
         patch("os.remove", side_effect=PermissionError("denied")):
        r = client.delete("/api/comics/1?permanent=true")
    assert r.status_code == 500


# ---------------------------------------------------------------------------
# api/system.py — backup_now error path
# ---------------------------------------------------------------------------

def test_backup_now_error_path(client, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with patch("api.system.backup_database", side_effect=RuntimeError("disk full")):
        r = client.post("/api/debug/backup-now")
    assert r.status_code == 200
    assert r.json()["status"] == "error"


# ---------------------------------------------------------------------------
# tasks/backup.py — exception path inside backup_database
# ---------------------------------------------------------------------------

def test_backup_exception_is_caught(tmp_path, monkeypatch):
    from tasks.backup import backup_database
    monkeypatch.chdir(tmp_path)
    (tmp_path / "prod.sqlite").write_bytes(b"db")
    with patch("shutil.copy2", side_effect=OSError("disk full")):
        asyncio.run(backup_database())  # Should not raise
