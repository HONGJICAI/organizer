"""Tests for decrypt_archives.py.

Real encrypted ZIPs are produced with the system ``zip`` CLI (traditional
ZipCrypto, which stdlib ``zipfile`` can read) so the ZIP path is exercised
end to end. The orchestration / error-handling paths are driven through a
``FakeHandler`` so they are deterministic and independent of any archive
format or external binary (e.g. unrar).
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys
import types
import zipfile

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import decrypt_archives as da  # noqa: E402

HAS_ZIP = shutil.which("zip") is not None
requires_zip = pytest.mark.skipif(not HAS_ZIP, reason="`zip` CLI not available")


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def make_encrypted_zip(path: pathlib.Path, password: str, files: dict[str, str]) -> None:
    src = path.parent / f"_src_{path.stem}"
    src.mkdir()
    for name, content in files.items():
        (src / name).write_text(content)
    subprocess.run(
        ["zip", "-q", "-r", "-P", password, str(path), "."],
        cwd=src,
        check=True,
    )
    shutil.rmtree(src)


def make_plain_zip(path: pathlib.Path, files: dict[str, str]) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)


def make_zip_with_raw_password(
    path: pathlib.Path, pwd_bytes: bytes, files: dict[str, str]
) -> None:
    """Create an encrypted zip whose password is exactly ``pwd_bytes``.

    The bytes are smuggled through argv via surrogateescape so we can build a
    fixture encrypted with, say, a GBK-encoded password.
    """
    src = path.parent / f"_src_{path.stem}"
    src.mkdir()
    for name, content in files.items():
        (src / name).write_text(content)
    arg = pwd_bytes.decode("utf-8", "surrogateescape")
    subprocess.run(
        ["zip", "-q", "-r", "-P", arg, str(path), "."], cwd=src, check=True
    )
    shutil.rmtree(src)


class FakeHandler(da.ArchiveHandler):
    """Configurable in-memory handler for exercising orchestration logic."""

    def __init__(
        self,
        path,
        *,
        encrypted=True,
        good_password="pw",
        files=None,
        read_raises=False,
        test_raises=False,
        raise_on_extract=False,
    ):
        super().__init__(path)
        self.encrypted = encrypted
        self.good_password = good_password
        self.files = files if files is not None else {"a.txt": "hi"}
        self.read_raises = read_raises
        self.test_raises = test_raises
        self.raise_on_extract = raise_on_extract

    def is_encrypted(self):
        if self.read_raises:
            raise OSError("cannot read header")
        return self.encrypted

    def test_password(self, password):
        if self.test_raises:
            raise RuntimeError("unexpected backend error")
        return password == self.good_password

    def extract_all(self, dest, password):
        # process_archive has already created `dest`.
        if self.raise_on_extract:
            (dest / "partial.bin").write_text("half written")
            raise RuntimeError("disk full")
        for name, content in self.files.items():
            (pathlib.Path(dest) / name).write_text(content)


def factory(**kwargs):
    return lambda path: FakeHandler(path, **kwargs)


# ---- fake rarfile module (no unrar/rarfile available in this environment) -- #
class _FakeRarError(Exception):
    pass


class _FakePasswordRequired(_FakeRarError):
    pass


class _FakeRarInfo:
    def __init__(self, name, isdir=False, needs_pw=False):
        self.name = name
        self._isdir = isdir
        self._needs = needs_pw

    def isdir(self):
        return self._isdir

    def needs_password(self):
        return self._needs


class _FakeStream:
    def __init__(self, data):
        self._data = data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, n=-1):
        data, self._data = self._data, b""
        return data


def make_fake_rarfile(config):
    """Build a stand-in for the ``rarfile`` module driven by ``config``."""
    mod = types.SimpleNamespace()
    mod.Error = _FakeRarError
    mod.PasswordRequired = _FakePasswordRequired

    class FakeRarFile:
        def __init__(self, path, pwd=None):
            self.pwd = pwd
            if config.get("header_encrypted") and pwd is None:
                raise _FakePasswordRequired("password required for listing")

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def needs_password(self):
            return config.get("needs_password", config.get("header_encrypted", False))

        def infolist(self):
            return config["infos"]

        def open(self, info, pwd=None):
            if pwd != config["good"]:
                raise _FakeRarError("bad password")
            return _FakeStream(b"payload")

        def extractall(self, path=None, pwd=None):
            if pwd != config["good"]:
                raise _FakeRarError("bad password")
            for info in config["infos"]:
                if not info.isdir():
                    (pathlib.Path(path) / info.name).write_text("payload")

    mod.RarFile = FakeRarFile
    return mod


# --------------------------------------------------------------------------- #
# load_passwords
# --------------------------------------------------------------------------- #
class TestLoadPasswords:
    def test_args_only(self):
        assert da.load_passwords(["a", "b"], None) == ["a", "b"]

    def test_dedup_preserves_order(self):
        assert da.load_passwords(["a", "b", "a", "c", "b"], None) == ["a", "b", "c"]

    def test_file_merge_and_blank_lines(self, tmp_path):
        pf = tmp_path / "pw.txt"
        pf.write_text("file1\n\n  spaced pw  \nfile2\n")
        assert da.load_passwords(["arg1"], str(pf)) == [
            "arg1",
            "file1",
            "  spaced pw  ",
            "file2",
        ]

    def test_file_and_args_dedup(self, tmp_path):
        pf = tmp_path / "pw.txt"
        pf.write_text("a\nb\n")
        assert da.load_passwords(["a"], str(pf)) == ["a", "b"]


# --------------------------------------------------------------------------- #
# password_byte_variants
# --------------------------------------------------------------------------- #
class TestPasswordVariants:
    def test_ascii_collapses_to_one(self):
        # ascii encodes identically across all code pages -> single variant
        assert da.password_byte_variants("secret") == [b"secret"]

    def test_chinese_yields_utf8_and_gbk(self):
        variants = da.password_byte_variants("测试")
        assert "测试".encode("utf-8") in variants
        assert "测试".encode("gbk") in variants
        # utf-8 and gbk forms differ, so both must be present and distinct
        assert "测试".encode("utf-8") != "测试".encode("gbk")

    def test_japanese_has_shift_jis(self):
        variants = da.password_byte_variants("パス")
        assert "パス".encode("shift_jis") in variants

    def test_unencodable_is_skipped(self):
        # latin-1 can't encode this; it must simply be absent, not raise
        variants = da.password_byte_variants("漢")
        assert all(v != b"" for v in variants)
        assert "漢".encode("utf-8") in variants


# --------------------------------------------------------------------------- #
# find_archives
# --------------------------------------------------------------------------- #
class TestFindArchives:
    def test_recursive_and_sorted(self, tmp_path):
        (tmp_path / "sub").mkdir()
        (tmp_path / "b.zip").write_text("x")
        (tmp_path / "sub" / "a.rar").write_text("x")
        (tmp_path / "note.txt").write_text("x")
        (tmp_path / "c.ZIP").write_text("x")  # case-insensitive ext
        found = da.find_archives(tmp_path)
        # sorted by full path, so top-level files come before the subdir
        assert [p.name for p in found] == ["b.zip", "c.ZIP", "a.rar"]

    def test_single_archive_file(self, tmp_path):
        f = tmp_path / "one.zip"
        f.write_text("x")
        assert da.find_archives(f) == [f]

    def test_single_non_archive_file(self, tmp_path):
        f = tmp_path / "one.txt"
        f.write_text("x")
        assert da.find_archives(f) == []

    def test_make_handler_unknown_extension(self, tmp_path):
        assert da.make_handler(tmp_path / "one.txt") is None

    def test_empty_dir(self, tmp_path):
        assert da.find_archives(tmp_path) == []


# --------------------------------------------------------------------------- #
# ZipHandler (real archives)
# --------------------------------------------------------------------------- #
@requires_zip
class TestZipHandler:
    def test_detects_encrypted(self, tmp_path):
        z = tmp_path / "e.zip"
        make_encrypted_zip(z, "secret", {"a.txt": "data"})
        assert da.ZipHandler(z).is_encrypted() is True

    def test_detects_plain(self, tmp_path):
        z = tmp_path / "p.zip"
        make_plain_zip(z, {"a.txt": "data"})
        assert da.ZipHandler(z).is_encrypted() is False

    def test_password_right_and_wrong(self, tmp_path):
        z = tmp_path / "e.zip"
        make_encrypted_zip(z, "secret", {"a.txt": "data"})
        h = da.ZipHandler(z)
        assert h.test_password("secret") is True
        assert h.test_password("nope") is False

    def test_empty_archive_password_trivially_ok(self, tmp_path):
        z = tmp_path / "empty.zip"
        with zipfile.ZipFile(z, "w"):
            pass
        assert da.ZipHandler(z).test_password("whatever") is True

    def test_gbk_password_unlocks_via_variant(self, tmp_path):
        # archive encrypted with the GBK byte form of a Chinese password
        z = tmp_path / "zh.zip"
        make_zip_with_raw_password(z, "测试".encode("gbk"), {"a.txt": "data"})
        h = da.ZipHandler(z)
        # UTF-8 form would not match; the handler must fall through to GBK
        assert h.test_password("测试") is True
        assert h._pwd_bytes == "测试".encode("gbk")

    def test_gbk_password_extracts_with_resolved_bytes(self, tmp_path):
        z = tmp_path / "zh.zip"
        make_zip_with_raw_password(z, "测试".encode("gbk"), {"a.txt": "payload"})
        res = da.process_archive(z, ["测试"])
        assert res.outcome is da.Outcome.EXTRACTED
        assert (tmp_path / "zh" / "a.txt").read_text() == "payload"

    def test_unicode_password_utf8(self, tmp_path):
        # zip(1) on a UTF-8 locale stores the password as UTF-8 bytes
        z = tmp_path / "u.zip"
        make_encrypted_zip(z, "密码123", {"a.txt": "data"})
        assert da.ZipHandler(z).test_password("密码123") is True

    def test_password_on_corrupt_archive_returns_false(self, tmp_path):
        z = tmp_path / "broken.zip"
        z.write_text("not a zip at all")
        assert da.ZipHandler(z).test_password("pw") is False


class TestZipNameRecovery:
    def _info(self, name, flag=0):
        zi = zipfile.ZipInfo(name)
        zi.flag_bits = flag
        return zi

    def test_recovers_gbk_name_without_utf8_flag(self, tmp_path):
        real = "漫画第01话.jpg"
        moji = real.encode("gbk").decode("cp437")  # what zipfile would show
        h = da.ZipHandler(tmp_path / "x.zip", filename_encoding="gbk")
        assert h._decode_name(self._info(moji, flag=0)) == real

    def test_keeps_name_when_utf8_flag_set(self, tmp_path):
        real = "漫画.jpg"
        h = da.ZipHandler(tmp_path / "x.zip", filename_encoding="gbk")
        # flag 0x800 means zipfile already decoded correctly -> leave untouched
        assert h._decode_name(self._info(real, flag=0x800)) == real

    def test_no_encoding_means_passthrough(self, tmp_path):
        moji = "漫画.jpg".encode("gbk").decode("cp437")
        h = da.ZipHandler(tmp_path / "x.zip", filename_encoding=None)
        assert h._decode_name(self._info(moji, flag=0)) == moji

    def test_undecodable_name_falls_back(self, tmp_path):
        h = da.ZipHandler(tmp_path / "x.zip", filename_encoding="gbk")
        # an ascii-only name round-trips cleanly to itself
        assert h._decode_name(self._info("plain.jpg", flag=0)) == "plain.jpg"

    def test_non_cp437_name_falls_back_unchanged(self, tmp_path):
        # a real unicode char can't be re-encoded as cp437 -> keep as-is
        h = da.ZipHandler(tmp_path / "x.zip", filename_encoding="gbk")
        assert h._decode_name(self._info("中文.jpg", flag=0)) == "中文.jpg"

    def test_safe_target_blocks_zip_slip(self, tmp_path):
        dest = tmp_path / "out"
        assert da.ZipHandler._safe_target(dest, "../../etc/passwd") == dest / "etc" / "passwd"
        assert da.ZipHandler._safe_target(dest, "/abs/path.txt") == dest / "abs" / "path.txt"
        assert da.ZipHandler._safe_target(dest, "a\\b\\c.txt") == dest / "a" / "b" / "c.txt"
        assert da.ZipHandler._safe_target(dest, "../..") is None


@requires_zip
class TestZipExtraction:
    def test_preserves_subdirs_and_binary(self, tmp_path):
        z = tmp_path / "c.zip"
        src = tmp_path / "src"
        (src / "sub").mkdir(parents=True)
        (src / "01.jpg").write_bytes(b"\x00\xff\x10cover")
        (src / "sub" / "02.jpg").write_bytes(b"\x89PNGdata")
        subprocess.run(
            ["zip", "-q", "-r", "-P", "pw", str(z), "."], cwd=src, check=True
        )
        shutil.rmtree(src)
        res = da.process_archive(z, ["pw"])
        assert res.outcome is da.Outcome.EXTRACTED
        out = tmp_path / "c"
        assert (out / "01.jpg").read_bytes() == b"\x00\xff\x10cover"
        assert (out / "sub" / "02.jpg").read_bytes() == b"\x89PNGdata"

    def test_filename_encoding_passthrough_for_ascii(self, tmp_path):
        # ascii names with --filename-encoding set must still extract correctly
        z = tmp_path / "a.zip"
        make_encrypted_zip(z, "pw", {"page.jpg": "x"})
        res = da.process_archive(
            z, ["pw"], handler_factory=lambda p: da.make_handler(p, "gbk")
        )
        assert res.outcome is da.Outcome.EXTRACTED
        assert (tmp_path / "a" / "page.jpg").read_text() == "x"

    def test_extract_all_password_fallback_without_test(self, tmp_path):
        # calling extract_all directly (no prior test_password) uses UTF-8 bytes
        z = tmp_path / "e.zip"
        make_encrypted_zip(z, "pw", {"a.txt": "data"})
        dest = tmp_path / "out"
        dest.mkdir()
        da.ZipHandler(z).extract_all(dest, "pw")
        assert (dest / "a.txt").read_text() == "data"

    def test_extract_all_skips_traversal_only_entry(self, tmp_path):
        # an entry whose name normalizes to nothing must be skipped, not written
        z = tmp_path / "p.zip"
        with zipfile.ZipFile(z, "w") as zf:
            zf.writestr("ok.txt", "good")
            zf.writestr("..", "evil")
        dest = tmp_path / "out"
        dest.mkdir()
        da.ZipHandler(z).extract_all(dest, None)
        assert (dest / "ok.txt").read_text() == "good"
        assert not (dest / "..").exists() or not (dest.parent / "evil").exists()

    def test_extract_all_rejects_colliding_entries(self, tmp_path):
        # "x.txt" and "./x.txt" both resolve to dest/x.txt -> refuse the archive
        z = tmp_path / "dup.zip"
        with zipfile.ZipFile(z, "w") as zf:
            zf.writestr("x.txt", "first")
            zf.writestr("./x.txt", "second")
        dest = tmp_path / "out"
        dest.mkdir()
        with pytest.raises(RuntimeError, match="same path"):
            da.ZipHandler(z).extract_all(dest, None)
        # nothing is written when a collision is detected
        assert list(dest.iterdir()) == []

    def test_collision_via_process_archive_keeps_source(self, tmp_path, monkeypatch):
        z = tmp_path / "dup.zip"
        with zipfile.ZipFile(z, "w") as zf:
            zf.writestr("x.txt", "first")
            zf.writestr("./x.txt", "second")
        # force the encrypted path so process_archive proceeds to extraction
        monkeypatch.setattr(da.ZipHandler, "is_encrypted", lambda self: True)
        monkeypatch.setattr(da.ZipHandler, "test_password", lambda self, pw: True)
        res = da.process_archive(z, ["pw"])
        assert res.outcome is da.Outcome.ERROR
        assert "same path" in res.detail
        assert z.exists()  # source kept
        assert not (tmp_path / "dup").exists()  # partial dest cleaned up


# --------------------------------------------------------------------------- #
# process_archive: end to end with real encrypted ZIPs
# --------------------------------------------------------------------------- #
@requires_zip
class TestProcessArchiveReal:
    def test_extracts_and_deletes_source(self, tmp_path):
        z = tmp_path / "comic.zip"
        make_encrypted_zip(z, "secret", {"01.jpg": "AAA", "02.jpg": "BBB"})
        res = da.process_archive(z, ["wrong", "secret"])
        assert res.outcome is da.Outcome.EXTRACTED
        assert res.password == "secret"
        assert res.deleted is True
        assert not z.exists()
        dest = tmp_path / "comic"
        assert (dest / "01.jpg").read_text() == "AAA"
        assert (dest / "02.jpg").read_text() == "BBB"

    def test_plain_archive_skipped(self, tmp_path):
        z = tmp_path / "plain.zip"
        make_plain_zip(z, {"a.txt": "data"})
        res = da.process_archive(z, ["secret"])
        assert res.outcome is da.Outcome.NOT_ENCRYPTED
        assert z.exists()
        assert not (tmp_path / "plain").exists()

    def test_no_password_matches_keeps_source(self, tmp_path):
        z = tmp_path / "e.zip"
        make_encrypted_zip(z, "secret", {"a.txt": "data"})
        res = da.process_archive(z, ["nope1", "nope2"])
        assert res.outcome is da.Outcome.NO_PASSWORD
        assert z.exists()
        assert not (tmp_path / "e").exists()

    def test_dry_run_changes_nothing(self, tmp_path):
        z = tmp_path / "e.zip"
        make_encrypted_zip(z, "secret", {"a.txt": "data"})
        res = da.process_archive(z, ["secret"], dry_run=True)
        assert res.outcome is da.Outcome.EXTRACTED
        assert res.deleted is False
        assert z.exists()
        assert not (tmp_path / "e").exists()

    def test_keep_source(self, tmp_path):
        z = tmp_path / "e.zip"
        make_encrypted_zip(z, "secret", {"a.txt": "data"})
        res = da.process_archive(z, ["secret"], keep_source=True)
        assert res.outcome is da.Outcome.EXTRACTED
        assert res.deleted is False
        assert z.exists()
        assert (tmp_path / "e" / "a.txt").read_text() == "data"

    def test_destination_conflict(self, tmp_path):
        z = tmp_path / "e.zip"
        make_encrypted_zip(z, "secret", {"a.txt": "data"})
        (tmp_path / "e").mkdir()  # pre-existing destination
        res = da.process_archive(z, ["secret"])
        assert res.outcome is da.Outcome.ERROR
        assert "already exists" in res.detail
        assert z.exists()  # source kept, not clobbered

    def test_corrupt_archive_is_error(self, tmp_path):
        z = tmp_path / "broken.zip"
        z.write_text("this is not a zip")
        res = da.process_archive(z, ["secret"])
        assert res.outcome is da.Outcome.ERROR
        assert "cannot read" in res.detail
        assert z.exists()


# --------------------------------------------------------------------------- #
# process_archive: orchestration / error paths via FakeHandler
# --------------------------------------------------------------------------- #
class TestProcessArchiveFake:
    def _archive(self, tmp_path):
        p = tmp_path / "x.zip"
        p.write_text("placeholder")
        return p

    def test_extraction_failure_cleans_up_and_keeps_source(self, tmp_path):
        p = self._archive(tmp_path)
        res = da.process_archive(
            p, ["pw"], handler_factory=factory(raise_on_extract=True)
        )
        assert res.outcome is da.Outcome.ERROR
        assert "extraction failed" in res.detail
        assert p.exists()  # source kept
        assert not (tmp_path / "x").exists()  # partial output removed

    def test_unsupported_format(self, tmp_path):
        p = tmp_path / "x.rar"
        p.write_text("placeholder")
        res = da.process_archive(p, ["pw"], handler_factory=lambda _p: None)
        assert res.outcome is da.Outcome.UNSUPPORTED

    def test_read_error_is_error(self, tmp_path):
        p = self._archive(tmp_path)
        res = da.process_archive(p, ["pw"], handler_factory=factory(read_raises=True))
        assert res.outcome is da.Outcome.ERROR
        assert "cannot read" in res.detail
        assert p.exists()

    def test_test_password_unexpected_error_is_swallowed(self, tmp_path):
        p = self._archive(tmp_path)
        # test_password raises for every candidate -> treated as no match.
        res = da.process_archive(p, ["pw"], handler_factory=factory(test_raises=True))
        assert res.outcome is da.Outcome.NO_PASSWORD
        assert p.exists()

    def test_not_encrypted_via_fake(self, tmp_path):
        p = self._archive(tmp_path)
        res = da.process_archive(p, ["pw"], handler_factory=factory(encrypted=False))
        assert res.outcome is da.Outcome.NOT_ENCRYPTED
        assert p.exists()

    def test_success_via_fake(self, tmp_path):
        p = self._archive(tmp_path)
        res = da.process_archive(
            p,
            ["bad", "pw"],
            handler_factory=factory(good_password="pw", files={"p.txt": "hello"}),
        )
        assert res.outcome is da.Outcome.EXTRACTED
        assert res.password == "pw"
        assert not p.exists()
        assert (tmp_path / "x" / "p.txt").read_text() == "hello"

    def test_extracted_but_delete_fails(self, tmp_path, monkeypatch):
        p = self._archive(tmp_path)

        def boom(self):
            raise OSError("read-only filesystem")

        monkeypatch.setattr(pathlib.Path, "unlink", boom)
        res = da.process_archive(p, ["pw"], handler_factory=factory())
        assert res.outcome is da.Outcome.ERROR
        assert "could not delete source" in res.detail
        assert res.extracted_to == tmp_path / "x"


# --------------------------------------------------------------------------- #
# run()
# --------------------------------------------------------------------------- #
@requires_zip
class TestRun:
    def test_multiple_archives_summary(self, tmp_path):
        make_encrypted_zip(tmp_path / "enc.zip", "secret", {"a.txt": "1"})
        make_plain_zip(tmp_path / "plain.zip", {"b.txt": "2"})
        make_encrypted_zip(tmp_path / "locked.zip", "other", {"c.txt": "3"})
        logs: list[str] = []
        results = da.run(tmp_path, ["secret"], log=logs.append)
        by_outcome = {r.path.name: r.outcome for r in results}
        assert by_outcome["enc.zip"] is da.Outcome.EXTRACTED
        assert by_outcome["plain.zip"] is da.Outcome.NOT_ENCRYPTED
        assert by_outcome["locked.zip"] is da.Outcome.NO_PASSWORD
        assert any("Summary:" in line for line in logs)
        assert not (tmp_path / "enc.zip").exists()
        assert (tmp_path / "locked.zip").exists()


# --------------------------------------------------------------------------- #
# main() / CLI
# --------------------------------------------------------------------------- #
class TestMain:
    def test_missing_path(self, tmp_path, capsys):
        rc = da.main([str(tmp_path / "nope"), "-p", "x"])
        assert rc == 2
        assert "does not exist" in capsys.readouterr().err

    def test_no_passwords(self, tmp_path, capsys):
        rc = da.main([str(tmp_path)])
        assert rc == 2
        assert "no passwords" in capsys.readouterr().err

    @requires_zip
    def test_full_run_success_exit_zero(self, tmp_path):
        make_encrypted_zip(tmp_path / "e.zip", "secret", {"a.txt": "data"})
        rc = da.main([str(tmp_path), "-p", "secret"])
        assert rc == 0
        assert not (tmp_path / "e.zip").exists()
        assert (tmp_path / "e" / "a.txt").read_text() == "data"

    @requires_zip
    def test_failure_exit_one(self, tmp_path):
        make_encrypted_zip(tmp_path / "e.zip", "secret", {"a.txt": "data"})
        rc = da.main([str(tmp_path), "-p", "wrong"])
        assert rc == 1
        assert (tmp_path / "e.zip").exists()

    @requires_zip
    def test_filename_encoding_flag(self, tmp_path):
        make_encrypted_zip(tmp_path / "e.zip", "secret", {"a.txt": "data"})
        rc = da.main([str(tmp_path), "-p", "secret", "--filename-encoding", "gbk"])
        assert rc == 0
        assert (tmp_path / "e" / "a.txt").read_text() == "data"

    @requires_zip
    def test_password_file_flag(self, tmp_path):
        make_encrypted_zip(tmp_path / "e.zip", "secret", {"a.txt": "data"})
        pf = tmp_path / "pw.txt"
        pf.write_text("nope\nsecret\n")
        rc = da.main([str(tmp_path), "-f", str(pf)])
        assert rc == 0
        assert not (tmp_path / "e.zip").exists()


# --------------------------------------------------------------------------- #
# RarHandler (via a fake rarfile module)
# --------------------------------------------------------------------------- #
class TestRarHandler:
    def _install(self, monkeypatch, config):
        monkeypatch.setattr(da, "rarfile", make_fake_rarfile(config))

    def test_make_handler_none_without_rarfile(self, monkeypatch, tmp_path):
        monkeypatch.setattr(da, "rarfile", None)
        assert da.make_handler(tmp_path / "x.rar") is None

    def test_make_handler_rar_with_rarfile(self, monkeypatch, tmp_path):
        self._install(monkeypatch, {"good": "p", "infos": []})
        assert isinstance(da.make_handler(tmp_path / "x.rar"), da.RarHandler)

    def test_header_encrypted_detected(self, monkeypatch, tmp_path):
        self._install(monkeypatch, {"header_encrypted": True, "good": "p", "infos": []})
        assert da.RarHandler(tmp_path / "x.rar").is_encrypted() is True

    def test_needs_password_flag_without_listing_error(self, monkeypatch, tmp_path):
        # listing succeeds (no header encryption) but the file reports it
        # needs a password anyway.
        self._install(
            monkeypatch, {"needs_password": True, "good": "p", "infos": []}
        )
        assert da.RarHandler(tmp_path / "x.rar").is_encrypted() is True

    def test_entry_encrypted_detected(self, monkeypatch, tmp_path):
        self._install(
            monkeypatch,
            {"good": "p", "infos": [_FakeRarInfo("a.jpg", needs_pw=True)]},
        )
        assert da.RarHandler(tmp_path / "x.rar").is_encrypted() is True

    def test_plain_rar_not_encrypted(self, monkeypatch, tmp_path):
        self._install(
            monkeypatch, {"good": "p", "infos": [_FakeRarInfo("a.jpg")]}
        )
        assert da.RarHandler(tmp_path / "x.rar").is_encrypted() is False

    def test_password_right_and_wrong(self, monkeypatch, tmp_path):
        self._install(
            monkeypatch,
            {"good": "secret", "infos": [_FakeRarInfo("a.jpg")]},
        )
        h = da.RarHandler(tmp_path / "x.rar")
        assert h.test_password("secret") is True
        assert h.test_password("nope") is False

    def test_empty_rar_password_ok(self, monkeypatch, tmp_path):
        self._install(monkeypatch, {"good": "secret", "infos": []})
        assert da.RarHandler(tmp_path / "x.rar").test_password("anything") is True

    def test_process_rar_end_to_end(self, monkeypatch, tmp_path):
        self._install(
            monkeypatch,
            {
                "header_encrypted": True,
                "good": "secret",
                "infos": [_FakeRarInfo("01.jpg"), _FakeRarInfo("d", isdir=True)],
            },
        )
        p = tmp_path / "comic.rar"
        p.write_text("placeholder")
        res = da.process_archive(p, ["wrong", "secret"])
        assert res.outcome is da.Outcome.EXTRACTED
        assert res.password == "secret"
        assert not p.exists()
        assert (tmp_path / "comic" / "01.jpg").read_text() == "payload"


# --------------------------------------------------------------------------- #
# run() logging branches
# --------------------------------------------------------------------------- #
class TestRunLogBranches:
    def test_dry_run_log(self, tmp_path):
        p = tmp_path / "a.zip"
        p.write_text("x")
        logs: list[str] = []
        da.run(
            tmp_path, ["pw"], dry_run=True, log=logs.append, handler_factory=factory()
        )
        assert any("would extract" in line for line in logs)

    def test_unsupported_and_error_logs(self, tmp_path):
        (tmp_path / "u.rar").write_text("x")
        (tmp_path / "err.zip").write_text("x")

        def fac(path):
            if path.name == "u.rar":
                return None
            return FakeHandler(path, raise_on_extract=True)

        logs: list[str] = []
        da.run(tmp_path, ["pw"], log=logs.append, handler_factory=fac)
        joined = "\n".join(logs)
        assert "[unsupported]" in joined
        assert "[error]" in joined


# --------------------------------------------------------------------------- #
# SevenZipHandler (via an injected fake 7z runner)
# --------------------------------------------------------------------------- #
class Fake7z:
    """Mimic the subset of `7z` CLI behaviour the handler relies on."""

    def __init__(
        self,
        *,
        encrypted=True,
        good_password="pw",
        header_encrypted=False,
        list_corrupt=False,
        files=None,
    ):
        self.encrypted = encrypted
        self.good_password = good_password
        self.header_encrypted = header_encrypted
        self.list_corrupt = list_corrupt
        self.files = files if files is not None else ["a.txt"]
        self.calls: list[list[str]] = []

    @staticmethod
    def _password(args):
        for a in args:
            if a.startswith("-p"):
                return a[2:]
        return None

    def __call__(self, args):
        self.calls.append(args)
        cmd = args[0]
        pw = self._password(args)
        if cmd == "l":
            if self.header_encrypted and not pw:
                return 2, "", "ERROR: Wrong password : archive"
            if self.list_corrupt:
                return 2, "", "ERROR: Cannot open the file as an archive"
            flag = "+" if self.encrypted else "-"
            body = "\n".join(
                f"Path = {name}\nEncrypted = {flag}\n" for name in self.files
            )
            return 0, body, ""
        if cmd == "t":
            if pw == self.good_password:
                return 0, "Everything is Ok\n", ""
            return 2, "", "ERROR: Wrong password?"
        if cmd == "x":
            if pw != self.good_password:
                return 2, "", "ERROR: Wrong password?"
            dest = next((a[2:] for a in args if a.startswith("-o")), None)
            if dest:
                for name in self.files:
                    target = pathlib.Path(dest) / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text("payload")
            return 0, "Everything is Ok\n", ""
        return 7, "", "ERROR: bad command line"


def sevenzip_handler(path, **kwargs):
    return da.SevenZipHandler(path, "7z", runner=Fake7z(**kwargs))


class TestSevenZipHandler:
    def test_detects_encrypted_content(self, tmp_path):
        h = sevenzip_handler(tmp_path / "x.zip", encrypted=True)
        assert h.is_encrypted() is True

    def test_detects_plain(self, tmp_path):
        h = sevenzip_handler(tmp_path / "x.zip", encrypted=False)
        assert h.is_encrypted() is False

    def test_header_encrypted_detected(self, tmp_path):
        h = sevenzip_handler(tmp_path / "x.7z", header_encrypted=True)
        assert h.is_encrypted() is True

    def test_corrupt_listing_raises(self, tmp_path):
        h = sevenzip_handler(tmp_path / "x.7z", list_corrupt=True)
        with pytest.raises(RuntimeError):
            h.is_encrypted()

    def test_password_right_and_wrong(self, tmp_path):
        h = sevenzip_handler(tmp_path / "x.rar", good_password="secret")
        assert h.test_password("secret") is True
        assert h.test_password("nope") is False

    def test_extract_writes_files(self, tmp_path):
        runner = Fake7z(good_password="secret", files=["sub/01.jpg", "02.jpg"])
        h = da.SevenZipHandler(tmp_path / "x.rar", "7z", runner=runner)
        dest = tmp_path / "out"
        dest.mkdir()
        h.extract_all(dest, "secret")
        assert (dest / "sub" / "01.jpg").read_text() == "payload"
        assert (dest / "02.jpg").read_text() == "payload"

    def test_extract_wrong_password_raises(self, tmp_path):
        h = sevenzip_handler(tmp_path / "x.rar", good_password="secret")
        with pytest.raises(RuntimeError):
            h.extract_all(tmp_path / "out", "wrong")

    def test_end_to_end_via_process_archive(self, tmp_path):
        p = tmp_path / "comic.cbr"
        p.write_text("placeholder")
        runner = Fake7z(good_password="secret", files=["01.jpg"])
        res = da.process_archive(
            p,
            ["wrong", "secret"],
            handler_factory=lambda path: da.SevenZipHandler(path, "7z", runner=runner),
        )
        assert res.outcome is da.Outcome.EXTRACTED
        assert res.password == "secret"
        assert not p.exists()
        assert (tmp_path / "comic" / "01.jpg").read_text() == "payload"

    def test_bad_command_treated_as_wrong_password_false(self, tmp_path):
        # an unexpected command yields a non-OK code -> test_password returns False
        h = da.SevenZipHandler(tmp_path / "x.zip", "7z", runner=lambda a: (7, "", "bad"))
        assert h.test_password("pw") is False

    def test_run_invokes_real_subprocess(self, tmp_path):
        # with no injected runner, _run shells out for real; use the Python
        # interpreter as a stand-in executable to exercise that path portably.
        h = da.SevenZipHandler(tmp_path / "x.zip", sys.executable)
        code, out, err = h._run(["-c", "print('hello-7z')"])
        assert code == 0
        assert "hello-7z" in out


@pytest.mark.skipif(shutil.which("7z") is None, reason="real 7z not installed")
class TestSevenZipReal:
    def test_real_7z_roundtrip(self, tmp_path):
        z = tmp_path / "e.zip"
        make_encrypted_zip(z, "secret", {"a.txt": "data"})
        res = da.process_archive(
            z, ["secret"], handler_factory=lambda p: da.make_handler(p, None, "7z")
        )
        assert res.outcome is da.Outcome.EXTRACTED
        assert (tmp_path / "e" / "a.txt").read_text() == "data"


# --------------------------------------------------------------------------- #
# find_7z + make_handler routing
# --------------------------------------------------------------------------- #
class TestFind7z:
    def test_found(self, monkeypatch):
        monkeypatch.setattr(da.shutil, "which", lambda n: "/usr/bin/7z" if n == "7z" else None)
        assert da.find_7z() == "/usr/bin/7z"

    def test_not_found(self, monkeypatch):
        monkeypatch.setattr(da.shutil, "which", lambda n: None)
        assert da.find_7z() is None


class TestMakeHandlerRouting:
    def test_sevenzip_handles_rar_without_rarfile(self, monkeypatch, tmp_path):
        monkeypatch.setattr(da, "rarfile", None)
        h = da.make_handler(tmp_path / "x.rar", sevenzip="7z")
        assert isinstance(h, da.SevenZipHandler)

    def test_sevenzip_handles_7z(self, tmp_path):
        assert isinstance(da.make_handler(tmp_path / "x.7z", sevenzip="7z"), da.SevenZipHandler)

    def test_7z_unsupported_without_sevenzip(self, tmp_path):
        assert da.make_handler(tmp_path / "x.7z") is None

    def test_cbz_routes_to_zip(self, tmp_path):
        assert isinstance(da.make_handler(tmp_path / "x.cbz"), da.ZipHandler)

    def test_cbr_routes_to_rar(self, monkeypatch, tmp_path):
        self_install = make_fake_rarfile({"good": "p", "infos": []})
        monkeypatch.setattr(da, "rarfile", self_install)
        assert isinstance(da.make_handler(tmp_path / "x.cbr"), da.RarHandler)


# --------------------------------------------------------------------------- #
# main() 7z option plumbing
# --------------------------------------------------------------------------- #
class TestMain7z:
    def test_auto_detect_not_found(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(da, "find_7z", lambda: None)
        rc = da.main([str(tmp_path), "-p", "x", "--7z"])
        assert rc == 2
        assert "no 7-Zip executable" in capsys.readouterr().err

    def test_explicit_path_missing(self, tmp_path, capsys):
        rc = da.main([str(tmp_path), "-p", "x", "--7z", str(tmp_path / "nope.exe")])
        assert rc == 2
        assert "not found" in capsys.readouterr().err

    def test_explicit_path_passed_through(self, tmp_path, monkeypatch):
        exe = tmp_path / "7z"
        exe.write_text("#!/bin/sh\n")
        captured = {}

        def fake_run(root, passwords, **kwargs):
            captured.update(kwargs)
            return []

        monkeypatch.setattr(da, "run", fake_run)
        rc = da.main([str(tmp_path), "-p", "x", "--7z", str(exe)])
        assert rc == 0
        assert captured["sevenzip"] == str(exe)

    def test_auto_detect_passed_through(self, tmp_path, monkeypatch):
        monkeypatch.setattr(da, "find_7z", lambda: "/usr/bin/7z")
        captured = {}
        monkeypatch.setattr(da, "run", lambda root, pw, **kw: captured.update(kw) or [])
        rc = da.main([str(tmp_path), "-p", "x", "--7z"])
        assert rc == 0
        assert captured["sevenzip"] == "/usr/bin/7z"
