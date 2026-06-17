import errno
import hashlib
import os
from unittest.mock import patch

from util import PathState, create_soft_link, probe_path, probe_paths, str2md5


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


# ---------------------------------------------------------------------------
# probe_path / probe_paths
# ---------------------------------------------------------------------------

def test_probe_present(tmp_path):
    f = tmp_path / "here.zip"
    f.write_text("x")
    assert probe_path(str(f)) == PathState.PRESENT


def test_probe_absent_when_parent_reachable(tmp_path):
    # Parent exists, file does not -> a real deletion.
    assert probe_path(str(tmp_path / "gone.zip")) == PathState.ABSENT


def test_probe_unknown_when_parent_unreachable(tmp_path):
    # File and its parent are both gone -> ambiguous; could be an unmounted
    # share rather than a deleted file, so we refuse to call it ABSENT.
    nested = tmp_path / "missing_mount" / "sub" / "file.zip"
    assert probe_path(str(nested), retries=0) == PathState.UNKNOWN


def test_probe_unknown_on_io_error(tmp_path):
    # A transient I/O error (e.g. ESTALE/ETIMEDOUT) must read as UNKNOWN, not
    # ABSENT — flipping a healthy file to "missing" on a blip is the footgun.
    f = tmp_path / "blip.zip"
    f.write_text("x")
    with patch("util.os.stat", side_effect=OSError(errno.ETIMEDOUT, "timed out")):
        assert probe_path(str(f), retries=1, backoff=0) == PathState.UNKNOWN


def test_probe_retries_then_recovers(tmp_path):
    f = tmp_path / "recover.zip"
    f.write_text("x")
    real_stat = os.stat
    calls = {"n": 0}

    def flaky(path, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError(errno.ETIMEDOUT, "timed out")
        return real_stat(path, *args, **kwargs)

    with patch("util.os.stat", side_effect=flaky):
        assert probe_path(str(f), retries=2, backoff=0) == PathState.PRESENT
    assert calls["n"] == 2


def test_probe_paths_empty():
    assert probe_paths([]) == []


def test_probe_paths_preserves_order(tmp_path):
    present = tmp_path / "a.zip"
    present.write_text("x")
    absent = tmp_path / "b.zip"
    states = probe_paths([str(present), str(absent)])
    assert states == [PathState.PRESENT, PathState.ABSENT]
