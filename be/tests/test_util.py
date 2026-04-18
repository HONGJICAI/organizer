import hashlib
import os

from util import create_soft_link, str2md5


def test_str2md5_known_value():
    expected = hashlib.md5(b"hello").hexdigest()
    assert str2md5("hello") == expected


def test_str2md5_empty():
    expected = hashlib.md5(b"").hexdigest()
    assert str2md5("") == expected


def test_str2md5_unicode():
    s = "日本語"
    expected = hashlib.md5(s.encode("utf-8")).hexdigest()
    assert str2md5(s) == expected


def test_create_soft_link_creates_link(tmp_path):
    src = tmp_path / "source.txt"
    src.write_text("data")
    dst = tmp_path / "link"
    create_soft_link(str(src), str(dst))
    assert dst.is_symlink()
    assert os.readlink(str(dst)) == str(src)


def test_create_soft_link_no_op_if_exists(tmp_path):
    src = tmp_path / "source.txt"
    src.write_text("data")
    dst = tmp_path / "link"
    create_soft_link(str(src), str(dst))
    # Calling again must not raise
    create_soft_link(str(src), str(dst))
    assert dst.is_symlink()
