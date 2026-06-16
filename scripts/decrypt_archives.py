#!/usr/bin/env python3
"""Recursively decrypt + extract password-protected comic archives.

Given a root path and a password table (a list of candidate passwords), this
walks the tree for ``.zip`` / ``.rar`` files, and for every archive that is
*actually encrypted* tries each candidate password until one works. On success
the archive is extracted into a sibling directory named after the archive and
the source file is deleted. Archives that are not encrypted are left untouched.

Safety rules (the "extraction failure" flow this is built around):

* The source archive is deleted **only** after a fully successful extraction.
* Any password is verified by fully reading the first entry (CRC check) before
  a real extraction is attempted, so a wrong password never deletes anything.
* If extraction raises part-way through, the partially written destination is
  removed and the source archive is kept.
* If the destination directory already exists it is treated as a conflict: the
  archive is skipped and the source kept (we never clobber existing data).

Encoding notes (Chinese / Japanese archives):

* Passwords are tried in several encodings (UTF-8, GBK, Big5, Shift-JIS,
  Latin-1), because archives made on a non-Unicode Windows locale store the
  password in the local code page, not UTF-8 — a CJK password that "looks
  right" otherwise silently fails.
* ZIP entry names: modern archives flag names as UTF-8 and extract correctly.
  Legacy ZIPs store names in the creator's code page with no flag; pass
  ``--filename-encoding gbk`` (or big5 / shift_jis) to recover them instead of
  getting mojibake. RAR names are handled by the unrar backend and need no
  flag.

Usage::

    python decrypt_archives.py /path/to/library --password secret --password hunter2
    python decrypt_archives.py /path/to/library --password-file passwords.txt
    python decrypt_archives.py /path/to/library -f pw.txt --dry-run --keep
    python decrypt_archives.py /path/to/library -f pw.txt --filename-encoding gbk

Exit code is non-zero if any archive ended in an error or could not be
decrypted with the supplied passwords.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import zipfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Iterable, List, Sequence

try:  # rarfile (and its external unrar/bsdtar backend) is optional
    import rarfile
except ImportError:  # pragma: no cover - exercised via monkeypatch in tests
    rarfile = None

ARCHIVE_EXTS = {".zip", ".rar"}

# Archives created on Chinese/Japanese systems often encode the password in the
# local code page rather than UTF-8 (WinRAR/Bandizip on a non-Unicode locale),
# so every candidate password is tried in each of these encodings.
PASSWORD_ENCODINGS = ("utf-8", "gbk", "big5", "shift_jis", "latin-1")


def password_byte_variants(password: str) -> List[bytes]:
    """Encode ``password`` in each supported encoding, de-duplicated, order-kept."""
    variants: List[bytes] = []
    for enc in PASSWORD_ENCODINGS:
        try:
            data = password.encode(enc)
        except UnicodeEncodeError:
            continue
        if data not in variants:
            variants.append(data)
    return variants


class Outcome(str, Enum):
    """Final state of processing a single archive."""

    EXTRACTED = "extracted"  # decrypted, extracted and (unless --keep) deleted
    NOT_ENCRYPTED = "not_encrypted"  # plain archive, left untouched
    NO_PASSWORD = "no_password"  # encrypted but no candidate password worked
    ERROR = "error"  # unreadable, dest conflict, or extraction failed
    UNSUPPORTED = "unsupported"  # .rar but rarfile/unrar is unavailable


@dataclass
class ArchiveResult:
    path: Path
    outcome: Outcome
    detail: str = ""
    password: str | None = None
    extracted_to: Path | None = None
    deleted: bool = False

    @property
    def ok(self) -> bool:
        """Whether this result counts as a clean run for the exit code."""
        return self.outcome in (Outcome.EXTRACTED, Outcome.NOT_ENCRYPTED)


# --------------------------------------------------------------------------- #
# Archive handlers
# --------------------------------------------------------------------------- #
class ArchiveHandler:
    """Minimal uniform interface over the supported archive formats."""

    def __init__(self, path: Path, filename_encoding: str | None = None):
        self.path = path
        self.filename_encoding = filename_encoding

    def is_encrypted(self) -> bool:  # pragma: no cover - abstract
        raise NotImplementedError

    def test_password(self, password: str) -> bool:  # pragma: no cover - abstract
        """Return True if ``password`` can decrypt the first entry."""
        raise NotImplementedError

    def extract_all(self, dest: Path, password: str | None) -> None:  # pragma: no cover
        """Extract every entry into ``dest``; raise on any failure."""
        raise NotImplementedError


class ZipHandler(ArchiveHandler):
    def __init__(self, path: Path, filename_encoding: str | None = None):
        super().__init__(path, filename_encoding)
        # Password bytes resolved by test_password, reused by extract_all so the
        # same encoding that unlocked the archive is the one we extract with.
        self._pwd_bytes: bytes | None = None

    @staticmethod
    def _first_file(zf: zipfile.ZipFile) -> zipfile.ZipInfo | None:
        for zi in zf.infolist():
            if not zi.is_dir():
                return zi
        return None

    def _decode_name(self, info: zipfile.ZipInfo) -> str:
        """Recover a legacy (non-UTF-8) filename using ``filename_encoding``.

        When the archive sets the UTF-8/EFS flag (bit 11) zipfile already
        decoded the name correctly. Otherwise it decoded the raw bytes as
        CP437; if the user told us the real code page we round-trip back to the
        original bytes and re-decode.
        """
        name = info.filename
        if not self.filename_encoding or info.flag_bits & 0x800:
            return name
        try:
            return name.encode("cp437").decode(self.filename_encoding)
        except (UnicodeEncodeError, UnicodeDecodeError):
            return name

    def is_encrypted(self) -> bool:
        with zipfile.ZipFile(self.path) as zf:
            return any(zi.flag_bits & 0x1 for zi in zf.infolist())

    def test_password(self, password: str) -> bool:
        try:
            with zipfile.ZipFile(self.path) as zf:
                zi = self._first_file(zf)
                if zi is None:
                    self._pwd_bytes = b""  # empty archive: nothing to decrypt
                    return True
                for pwd in password_byte_variants(password):
                    try:
                        # Read the whole entry so a wrong password that slips
                        # past the 1-byte quick-check still fails on the CRC.
                        with zf.open(zi, pwd=pwd) as fh:
                            while fh.read(1 << 16):
                                pass
                        self._pwd_bytes = pwd
                        return True
                    except (RuntimeError, zipfile.BadZipFile, OSError):
                        continue
        except (zipfile.BadZipFile, OSError):
            pass
        return False

    @staticmethod
    def _safe_target(dest: Path, name: str) -> Path | None:
        """Map an archive entry name to a path under ``dest`` (blocks Zip Slip)."""
        parts = [
            p
            for p in name.replace("\\", "/").split("/")
            if p not in ("", ".", "..")
        ]
        if not parts:
            return None
        return dest.joinpath(*parts)

    def extract_all(self, dest: Path, password: str | None) -> None:
        pwd = self._pwd_bytes
        if pwd is None and password is not None:
            pwd = password.encode()
        with zipfile.ZipFile(self.path) as zf:
            if pwd:
                zf.setpassword(pwd)
            for info in zf.infolist():
                name = self._decode_name(info)
                if info.is_dir() or name.endswith("/"):
                    target = self._safe_target(dest, name)
                    if target is not None:
                        target.mkdir(parents=True, exist_ok=True)
                    continue
                target = self._safe_target(dest, name)
                if target is None:
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src, open(target, "wb") as out:
                    shutil.copyfileobj(src, out)


class RarHandler(ArchiveHandler):
    def _open(self, password: str | None = None):
        # Header-encrypted RARs need the password even to list contents, so we
        # pass it to the constructor when we have one.
        return rarfile.RarFile(self.path, pwd=password)

    def is_encrypted(self) -> bool:
        try:
            with self._open() as rf:
                if rf.needs_password():
                    return True
                return any(i.needs_password() for i in rf.infolist())
        except rarfile.PasswordRequired:
            # Couldn't even list entries without a password -> encrypted.
            return True

    @staticmethod
    def _first_file(rf) -> object | None:
        for info in rf.infolist():
            if not info.isdir():
                return info
        return None

    def test_password(self, password: str) -> bool:
        try:
            with self._open(password) as rf:
                info = self._first_file(rf)
                if info is None:
                    return True
                with rf.open(info, pwd=password) as fh:
                    while fh.read(1 << 16):
                        pass
            return True
        except rarfile.Error:
            return False

    def extract_all(self, dest: Path, password: str | None) -> None:
        with self._open(password) as rf:
            rf.extractall(path=str(dest), pwd=password)


def make_handler(
    path: Path, filename_encoding: str | None = None
) -> ArchiveHandler | None:
    """Return a handler for ``path`` or None if the format isn't supported."""
    ext = path.suffix.lower()
    if ext == ".zip":
        return ZipHandler(path, filename_encoding)
    if ext == ".rar":
        if rarfile is None:
            return None
        return RarHandler(path, filename_encoding)
    return None


# --------------------------------------------------------------------------- #
# Core logic
# --------------------------------------------------------------------------- #
def load_passwords(values: Sequence[str], password_file: str | None) -> List[str]:
    """Combine ``--password`` values with lines from ``--password-file``.

    Blank lines in the file are ignored. Order is preserved and duplicates are
    removed so each password is tried at most once.
    """
    passwords: List[str] = list(values)
    if password_file:
        with open(password_file, "r", encoding="utf-8") as fh:
            for line in fh:
                pw = line.rstrip("\r\n")
                if pw:
                    passwords.append(pw)
    seen: set[str] = set()
    unique: List[str] = []
    for pw in passwords:
        if pw not in seen:
            seen.add(pw)
            unique.append(pw)
    return unique


def find_archives(root: Path) -> List[Path]:
    """Recursively collect archive files under ``root`` (sorted, stable)."""
    if root.is_file():
        return [root] if root.suffix.lower() in ARCHIVE_EXTS else []
    found: List[Path] = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            if os.path.splitext(name)[1].lower() in ARCHIVE_EXTS:
                found.append(Path(dirpath) / name)
    return sorted(found)


def _unique_dest(path: Path) -> Path:
    """Destination directory for an archive: sibling dir named after the stem."""
    return path.with_suffix("")


def process_archive(
    path: Path,
    passwords: Sequence[str],
    *,
    dry_run: bool = False,
    keep_source: bool = False,
    handler_factory: Callable[[Path], ArchiveHandler | None] = make_handler,
) -> ArchiveResult:
    """Decrypt, extract and (optionally) delete a single archive."""
    handler = handler_factory(path)
    if handler is None:
        return ArchiveResult(path, Outcome.UNSUPPORTED, detail="no handler for format")

    try:
        encrypted = handler.is_encrypted()
    except Exception as ex:  # unreadable / corrupt archive
        return ArchiveResult(path, Outcome.ERROR, detail=f"cannot read: {ex}")

    if not encrypted:
        return ArchiveResult(path, Outcome.NOT_ENCRYPTED)

    # Find the first password that decrypts the archive.
    match: str | None = None
    for pw in passwords:
        try:
            if handler.test_password(pw):
                match = pw
                break
        except Exception:
            # A handler should swallow its own decryption errors, but never let
            # an unexpected one abort the whole run.
            continue
    if match is None:
        return ArchiveResult(
            path, Outcome.NO_PASSWORD, detail="no candidate password worked"
        )

    dest = _unique_dest(path)
    if dry_run:
        return ArchiveResult(
            path, Outcome.EXTRACTED, password=match, extracted_to=dest, deleted=False
        )

    if dest.exists():
        return ArchiveResult(
            path,
            Outcome.ERROR,
            password=match,
            detail=f"destination already exists: {dest}",
        )

    # Extract. On any failure remove the partial output and keep the source.
    try:
        dest.mkdir(parents=True)
        handler.extract_all(dest, match)
    except Exception as ex:
        shutil.rmtree(dest, ignore_errors=True)
        return ArchiveResult(
            path, Outcome.ERROR, password=match, detail=f"extraction failed: {ex}"
        )

    deleted = False
    if not keep_source:
        try:
            path.unlink()
            deleted = True
        except OSError as ex:
            return ArchiveResult(
                path,
                Outcome.ERROR,
                password=match,
                extracted_to=dest,
                detail=f"extracted but could not delete source: {ex}",
            )

    return ArchiveResult(
        path, Outcome.EXTRACTED, password=match, extracted_to=dest, deleted=deleted
    )


def run(
    root: Path,
    passwords: Sequence[str],
    *,
    dry_run: bool = False,
    keep_source: bool = False,
    filename_encoding: str | None = None,
    log: Callable[[str], None] = print,
    handler_factory: Callable[[Path], ArchiveHandler | None] | None = None,
) -> List[ArchiveResult]:
    """Process every archive under ``root`` and return per-archive results."""
    if handler_factory is None:
        def handler_factory(path: Path) -> ArchiveHandler | None:
            return make_handler(path, filename_encoding)

    results: List[ArchiveResult] = []
    archives = find_archives(root)
    log(f"Found {len(archives)} archive(s) under {root}")
    for archive in archives:
        result = process_archive(
            archive,
            passwords,
            dry_run=dry_run,
            keep_source=keep_source,
            handler_factory=handler_factory,
        )
        _log_result(result, dry_run, log)
        results.append(result)
    _log_summary(results, log)
    return results


def _log_result(result: ArchiveResult, dry_run: bool, log: Callable[[str], None]) -> None:
    if result.outcome is Outcome.EXTRACTED:
        if dry_run:
            log(f"[would extract] {result.path} (password: {result.password!r})")
        else:
            tail = " (source deleted)" if result.deleted else " (source kept)"
            log(f"[extracted] {result.path} -> {result.extracted_to}{tail}")
    elif result.outcome is Outcome.NOT_ENCRYPTED:
        log(f"[skip] {result.path} (not encrypted)")
    elif result.outcome is Outcome.NO_PASSWORD:
        log(f"[no password] {result.path}")
    elif result.outcome is Outcome.UNSUPPORTED:
        log(f"[unsupported] {result.path} ({result.detail})")
    else:
        log(f"[error] {result.path} ({result.detail})")


def _log_summary(results: Iterable[ArchiveResult], log: Callable[[str], None]) -> None:
    counts: dict[Outcome, int] = {}
    for r in results:
        counts[r.outcome] = counts.get(r.outcome, 0) + 1
    parts = [f"{outcome.value}={counts.get(outcome, 0)}" for outcome in Outcome]
    log("Summary: " + ", ".join(parts))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Recursively decrypt and extract password-protected comic archives."
    )
    parser.add_argument("root", type=Path, help="root directory (or single archive) to scan")
    parser.add_argument(
        "-p",
        "--password",
        action="append",
        default=[],
        dest="passwords",
        help="a candidate password (repeatable)",
    )
    parser.add_argument(
        "-f",
        "--password-file",
        help="file with one candidate password per line",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would happen without extracting or deleting",
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        dest="keep_source",
        help="extract but do not delete the source archive",
    )
    parser.add_argument(
        "--filename-encoding",
        help=(
            "code page for legacy (non-UTF-8) ZIP entry names, e.g. gbk, big5, "
            "shift_jis. Only applied to entries without the UTF-8 flag."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if not args.root.exists():
        print(f"error: path does not exist: {args.root}", file=sys.stderr)
        return 2

    passwords = load_passwords(args.passwords, args.password_file)
    if not passwords:
        print("error: no passwords supplied (use --password or --password-file)", file=sys.stderr)
        return 2

    results = run(
        args.root,
        passwords,
        dry_run=args.dry_run,
        keep_source=args.keep_source,
        filename_encoding=args.filename_encoding,
    )
    failed = any(not r.ok for r in results)
    return 1 if failed else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
