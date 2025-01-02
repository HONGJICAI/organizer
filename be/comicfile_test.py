import pathlib
import pytest
import zipfile

import rarfile

import comicfile


def test_create():
    assert isinstance(comicfile.create("test.zip"), comicfile.ZipComicfile)
    assert isinstance(comicfile.create("test.rar"), comicfile.RarComicfile)
    assert isinstance(comicfile.create("test"), comicfile.DirectoryComicfile)
    assert comicfile.create("test.jpg") is None

def test_comicfile_zip(tmp_path: pathlib.Path):
    path = tmp_path / "test.zip"
    file = zipfile.ZipFile(path, "w")
    for i in range(2):
        file.writestr(f"{i}.jpg", b"placeholder")
    file.close()
    zf = comicfile.ZipComicfile(path)
    with zf:
        assert zf.page == 2
        zf.open()
        ok, buf = zf.read(0)
        assert ok

# def test_comicfile_rar(tmp_path: pathlib.Path):
#     path = tmp_path / "test.rar"
#     file = rarfile.RarFile(path, "w")
#     for i in range(2):
#         file.writestr(f"{i}.jpg", b"placeholder")
#     file.close()
#     rf = comicfile.RarComicfile(path)
#     with rf:
#         assert rf.page == 2
#         rf.open()
#         ok, buf = rf.read(0)
#         assert ok

def test_comicfile_directory(tmp_path: pathlib.Path):
    path = tmp_path / "test"
    path.mkdir()
    for i in range(2):
        (path / f"{i}.jpg").write_text("placeholder")
    df = comicfile.DirectoryComicfile(path)
    with df:
        assert df.page == 2
        df.open()
        ok, buf = df.read(0)
        assert ok