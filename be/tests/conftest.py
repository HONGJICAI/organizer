import io
import zipfile
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

import comicfile
import db
import global_data
from model import ComicEntity, VideoEntity


# ---------------------------------------------------------------------------
# Image / file helpers
# ---------------------------------------------------------------------------

def make_jpeg_bytes() -> bytes:
    img = Image.new("RGB", (10, 10), color=(128, 128, 128))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def make_zip_comic(path, pages: int = 3) -> None:
    jpeg = make_jpeg_bytes()
    with zipfile.ZipFile(path, "w") as zf:
        for i in range(pages):
            zf.writestr(f"{i:04d}.jpg", jpeg)


# ---------------------------------------------------------------------------
# DB entity helpers (plain functions – call from tests with the session fixture)
# ---------------------------------------------------------------------------

def insert_comic(
    session: Session,
    id: int = 1,
    name: str = "test.zip",
    path: str = "/nonexistent/test.zip",
    page: int = 3,
    **kwargs,
) -> ComicEntity:
    comic = ComicEntity(
        id=id, name=name, path=path, size=1000,
        updateTime=datetime.now(), page=page, **kwargs,
    )
    session.add(comic)
    session.commit()
    return comic


def insert_video(
    session: Session,
    id: int = 1,
    name: str = "test.mp4",
    path: str = "/nonexistent/test.mp4",
    duration: int = 60,
    **kwargs,
) -> VideoEntity:
    video = VideoEntity(
        id=id, name=name, path=path, size=1000,
        updateTime=datetime.now(), durationInSecond=duration, **kwargs,
    )
    session.add(video)
    session.commit()
    return video


# ---------------------------------------------------------------------------
# Mock comicfile
# ---------------------------------------------------------------------------

class MockComicfile:
    def __init__(self, pages: int = 3):
        self._pages = pages
        self._namelist = [f"{i:04d}.jpg" for i in range(pages)]
        self._opened = True

    @property
    def page(self) -> int:
        return self._pages

    @property
    def namelist(self):
        return self._namelist

    def read(self, page_idx: int):
        if page_idx >= self._pages:
            return False, None
        return True, make_jpeg_bytes()

    def close(self):
        pass


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_module_caches():
    comicfile.comic_cache.clear()
    yield
    comicfile.comic_cache.clear()


@pytest.fixture
def engine_and_client(tmp_path, monkeypatch):
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(test_engine)
    # Patch db.engine so lifespan tasks (cleanup_missing_comics) use test DB.
    monkeypatch.setattr(db, "engine", test_engine)

    for subdir in ("comics", "videos", "images"):
        (tmp_path / subdir).mkdir()
    monkeypatch.setattr(global_data.Config, "nginx_comic_path", str(tmp_path / "comics"))
    monkeypatch.setattr(global_data.Config, "nginx_video_path", str(tmp_path / "videos"))
    monkeypatch.setattr(global_data.Config, "nginx_image_path", str(tmp_path / "images"))

    def get_session_override():
        with Session(test_engine) as session:
            yield session

    from main import app
    app.dependency_overrides[db.get_session] = get_session_override

    # Suppress only the boot scan: swap in a no-op, start the client (which
    # fires the lifespan thread), then restore the real function so that tests
    # calling /api/system/scan get the genuine implementation.
    import api.system as _sys_mod
    real_run_scan = _sys_mod._run_scan
    _sys_mod._run_scan = lambda *a, **kw: None
    with TestClient(app) as c:
        _sys_mod._run_scan = real_run_scan
        yield test_engine, c

    app.dependency_overrides.clear()


@pytest.fixture
def client(engine_and_client):
    _, c = engine_and_client
    return c


@pytest.fixture
def session(engine_and_client):
    engine, _ = engine_and_client
    with Session(engine) as s:
        yield s


# Standalone engine fixture for task tests (no HTTP client needed).
@pytest.fixture
def task_engine(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(db, "engine", engine)
    return engine


@pytest.fixture
def task_session(task_engine):
    with Session(task_engine) as s:
        yield s
