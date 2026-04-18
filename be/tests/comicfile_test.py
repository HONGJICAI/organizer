import zipfile

import pytest

import comicfile
from conftest import make_jpeg_bytes, make_zip_comic


# ---------------------------------------------------------------------------
# create()
# ---------------------------------------------------------------------------

def test_create_nonexistent_returns_none():
    assert comicfile.create("nonexistent_file_xyz.zip") is None


def test_create_unsupported_extension_returns_none(tmp_path):
    f = tmp_path / "image.jpg"
    f.write_bytes(make_jpeg_bytes())
    assert comicfile.create(str(f)) is None


def test_create_zip(tmp_path):
    path = tmp_path / "test.zip"
    make_zip_comic(str(path))
    cf = comicfile.create(str(path))
    assert isinstance(cf, comicfile.ZipComicfile)


def test_create_directory(tmp_path):
    d = tmp_path / "mycomic"
    d.mkdir()
    (d / "0.jpg").write_bytes(make_jpeg_bytes())
    cf = comicfile.create(str(d))
    assert isinstance(cf, comicfile.DirectoryComicfile)


# ---------------------------------------------------------------------------
# ZipComicfile
# ---------------------------------------------------------------------------

def test_comicfile_zip(tmp_path):
    path = tmp_path / "test.zip"
    make_zip_comic(str(path), pages=2)
    zf = comicfile.ZipComicfile(str(path))
    with zf:
        assert zf.page == 2
        ok, buf = zf.read(0)
        assert ok
        assert buf is not None


def test_comicfile_zip_page_out_of_range(tmp_path):
    path = tmp_path / "test.zip"
    make_zip_comic(str(path), pages=2)
    with comicfile.ZipComicfile(str(path)) as zf:
        ok, buf = zf.read(99)
        assert not ok
        assert buf is None


def test_comicfile_zip_namelist(tmp_path):
    path = tmp_path / "test.zip"
    make_zip_comic(str(path), pages=3)
    with comicfile.ZipComicfile(str(path)) as zf:
        assert len(zf.namelist) == 3


def test_comicfile_zip_namelist_not_opened_raises(tmp_path):
    path = tmp_path / "test.zip"
    make_zip_comic(str(path), pages=1)
    zf = comicfile.ZipComicfile(str(path))
    with pytest.raises(Exception):
        _ = zf.namelist


def test_comicfile_zip_numeric_sort(tmp_path):
    jpeg = make_jpeg_bytes()
    path = tmp_path / "nums.zip"
    with zipfile.ZipFile(str(path), "w") as z:
        for name in ["10.jpg", "2.jpg", "1.jpg"]:
            z.writestr(name, jpeg)
    with comicfile.ZipComicfile(str(path)) as zf:
        assert zf.namelist[0] == "1.jpg"
        assert zf.namelist[1] == "2.jpg"
        assert zf.namelist[2] == "10.jpg"


def test_comicfile_zip_filters_non_images(tmp_path):
    path = tmp_path / "mixed.zip"
    with zipfile.ZipFile(str(path), "w") as z:
        z.writestr("0.jpg", make_jpeg_bytes())
        z.writestr("readme.txt", b"text")
        z.writestr("1.png", make_jpeg_bytes())
    with comicfile.ZipComicfile(str(path)) as zf:
        assert zf.page == 2


# ---------------------------------------------------------------------------
# DirectoryComicfile
# ---------------------------------------------------------------------------

def test_comicfile_directory(tmp_path):
    path = tmp_path / "test"
    path.mkdir()
    for i in range(2):
        (path / f"{i}.jpg").write_bytes(make_jpeg_bytes())
    df = comicfile.DirectoryComicfile(str(path))
    with df:
        assert df.page == 2
        ok, buf = df.read(0)
        assert ok
        assert buf is not None


def test_comicfile_directory_filters_non_images(tmp_path):
    d = tmp_path / "comics"
    d.mkdir()
    (d / "0.jpg").write_bytes(make_jpeg_bytes())
    (d / "notes.txt").write_text("hello")
    with comicfile.DirectoryComicfile(str(d)) as df:
        assert df.page == 1


def test_comicfile_directory_page_out_of_range(tmp_path):
    d = tmp_path / "c"
    d.mkdir()
    (d / "0.jpg").write_bytes(make_jpeg_bytes())
    with comicfile.DirectoryComicfile(str(d)) as df:
        ok, buf = df.read(99)
        assert not ok


# ---------------------------------------------------------------------------
# create_open() cached accessor
# ---------------------------------------------------------------------------

def test_create_open_returns_opened_comic(tmp_path):
    path = tmp_path / "open.zip"
    make_zip_comic(str(path), pages=2)
    cf = comicfile.create_open(str(path))
    assert cf is not None
    assert cf.page == 2


def test_create_open_nonexistent_returns_none():
    result = comicfile.create_open("/nonexistent/path.zip")
    assert result is None


def test_create_open_cached(tmp_path):
    path = tmp_path / "cached.zip"
    make_zip_comic(str(path), pages=1)
    cf1 = comicfile.create_open(str(path))
    cf2 = comicfile.create_open(str(path))
    assert cf1 is cf2
