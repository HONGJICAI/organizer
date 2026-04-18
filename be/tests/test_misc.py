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


# ---------------------------------------------------------------------------
# tasks/cache.py — error handling in loop
# ---------------------------------------------------------------------------

def test_cache_loop_cancelled():
    import asyncio
    from tasks.cache import process_comic_access_cache_loop

    async def run():
        task = asyncio.create_task(process_comic_access_cache_loop())
        await asyncio.sleep(0)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(run())
