"""SMB shares as media sources: the app mounts them itself.

Docker can mount an SMB share as a volume, but then the container doesn't
start while the share is unreachable. Mounted from here instead, a share that
is down only leaves its source held (see sources.py) and is retried: by every
scan, by ``reconnect_loop`` every few minutes, and by Admin -> Media sources.

Each share is mounted with the kernel's CIFS client (``mount.cifs`` from
cifs-utils) at ``<SMB_MOUNT_PATH>/<random name>``, chosen when the share is
added and never changed or reused, so records keep their paths. Mounting needs root and the SYS_ADMIN capability
(``cap_add`` in compose.yaml); without them the share shows why it isn't
connected and nothing else is affected. The password goes to mount.cifs in a
credentials file only root can read, removed right after, never on the command
line.
"""
import asyncio
import os
import re
import shutil
import subprocess
import tempfile
import threading
import uuid
from collections import defaultdict
from typing import Dict, List, Optional

from sqlmodel import Session, select

import db
from model import MediaSource

MOUNT_ROOT = os.environ.get("SMB_MOUNT_PATH", "/data/smb")
# A dead server makes calls fail after a timeout instead of hanging (soft),
# and names are UTF-8 on the wire. Options set on the source come after these.
DEFAULT_OPTIONS = ["iocharset=utf8", "soft"]
TIMEOUT = 45
RECONNECT_SECONDS = 300

# Set from the source's own fields (or the credentials file), not options.
_RESERVED = {"user", "username", "pass", "password", "password2", "cred", "credentials",
             "dom", "domain", "workgroup", "guest"}
_OPTION = re.compile(r"^[A-Za-z0-9_]+(=[A-Za-z0-9_.:/\-]+)?$")

_errors: Dict[int, str] = {}
_locks: Dict[int, threading.Lock] = defaultdict(threading.Lock)
_locks_guard = threading.Lock()


class SmbError(Exception):
    """A share setting that can't be used; the message says why."""


def new_mount_point() -> str:
    """A mount point for a new share: a random name, so it is never one a
    removed share had (records of that share keep pointing there)."""
    while True:
        path = os.path.join(MOUNT_ROOT, uuid.uuid4().hex[:12])
        if not os.path.exists(path):
            return path


def is_mounted(path: str) -> bool:
    return os.path.ismount(path)


def _run(args: List[str], timeout: float) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout)


_CAP_SYS_ADMIN = 21


def _has_sys_admin() -> Optional[bool]:
    """Whether this process may mount (CAP_SYS_ADMIN); None when unknown."""
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("CapEff:"):
                    return bool(int(line.split()[1], 16) >> _CAP_SYS_ADMIN & 1)
    except (OSError, ValueError, IndexError):
        pass
    return None


def unsupported() -> Optional[str]:
    """Why shares can't be mounted here, or None."""
    if os.name == "nt" or shutil.which("mount.cifs") is None:
        return "Mounting SMB shares needs mount.cifs (cifs-utils), which isn't installed here"
    if os.geteuid() != 0 or _has_sys_admin() is False:
        return (
            "Mounting SMB shares needs root with the SYS_ADMIN capability: "
            "uncomment cap_add in compose.yaml and recreate the container"
        )
    return None


def normalize_share(share: str) -> str:
    """``//host/share[/folder]`` from what people type: backslashes
    (``\\\\nas\\media``) and an ``smb:`` prefix are accepted."""
    share = (share or "").strip().replace("\\", "/")
    if share.lower().startswith("smb:"):
        share = share[4:]
    if any(ord(c) < 32 for c in share) or "," in share:
        raise SmbError("The share address has characters that can't be used")
    parts = [p for p in share.split("/") if p]
    if not share.startswith("//") or len(parts) < 2:
        raise SmbError(r"Enter the share as //server/share or \\server\share, optionally with a folder after it")
    return "//" + "/".join(parts)


def normalize_options(options: Optional[str]) -> str:
    """Extra mount.cifs options, comma-separated (e.g. ``vers=2.0``)."""
    items = [o.strip() for o in (options or "").split(",") if o.strip()]
    for item in items:
        if not _OPTION.match(item):
            raise SmbError(f"Invalid mount option {item!r}")
        if item.split("=", 1)[0].lower() in _RESERVED:
            raise SmbError(f"Set {item.split('=', 1)[0]!r} with the user name, password and domain fields")
    return ",".join(items)


def check_credential(value: Optional[str], what: str) -> str:
    value = value or ""
    if "\n" in value or "\r" in value or "\0" in value:
        raise SmbError(f"The {what} can't contain line breaks")
    return value


_HINTS = {
    1: "Not permitted: the container needs the SYS_ADMIN capability to mount shares (see compose.yaml)",
    2: "Share or folder not found on the server",
    13: "Permission denied: check the user name and password",
    19: "The kernel here has no CIFS (SMB) support",
    95: "The server doesn't speak this protocol version: try vers=2.0 or vers=1.0 in the options",
    101: "Can't reach the server",
    110: "Can't reach the server (timed out)",
    111: "The server refused the connection (is file sharing on?)",
    112: "Can't reach the server (it's down)",
    113: "Can't reach the server (no route to it)",
}


def explain(output: str) -> str:
    """A readable reason from mount.cifs's output."""
    lines = [line.strip() for line in (output or "").splitlines() if line.strip()]
    lines = [line for line in lines if not line.startswith("Refer to the")]
    raw = lines[0] if lines else "mount.cifs failed"
    match = re.search(r"mount error\((\d+)\)", output or "")
    hint = _HINTS.get(int(match.group(1))) if match else None
    return f"{hint} ({raw})" if hint else raw


def _lock(id: int) -> threading.Lock:
    with _locks_guard:
        return _locks[id]


def _mount(row: MediaSource) -> Optional[str]:
    reason = unsupported()
    if reason:
        return reason
    try:
        os.makedirs(row.path, exist_ok=True)
    except OSError as e:
        return f"Can't create the mount point {row.path}: {e.strerror or e}"
    options = list(DEFAULT_OPTIONS)
    cred = None
    if row.smbUsername:
        # mkstemp creates the file readable by its owner (root) only.
        fd, cred = tempfile.mkstemp(prefix="smb-cred-")
        with os.fdopen(fd, "w") as f:
            f.write(f"username={row.smbUsername}\n")
            f.write(f"password={row.smbPassword or ''}\n")
            if row.smbDomain:
                f.write(f"domain={row.smbDomain}\n")
        options.append(f"credentials={cred}")
    else:
        options.append("guest")
        if row.smbDomain:
            options.append(f"domain={row.smbDomain}")
    if row.smbOptions:
        options.append(row.smbOptions)
    try:
        result = _run(["mount.cifs", row.smbShare, row.path, "-o", ",".join(options)], TIMEOUT)
    except subprocess.TimeoutExpired:
        return f"Timed out after {TIMEOUT}s connecting to {row.smbShare}"
    finally:
        if cred:
            os.remove(cred)
    if result.returncode != 0:
        return explain(result.stderr or result.stdout)
    return None


def unmount(path: str) -> Optional[str]:
    """Unmount ``path`` if it is mounted (lazily when it's busy or the server
    is gone); returns why it couldn't be, or None."""
    if not is_mounted(path):
        return None
    for args in (["umount", path], ["umount", "-l", path]):
        try:
            result = _run(args, TIMEOUT)
        except subprocess.TimeoutExpired:
            continue
        if result.returncode == 0:
            return None
    return f"Couldn't unmount {path}"


def connect(row: MediaSource, remount: bool = False) -> Optional[str]:
    """Mount the share of ``row`` unless it already is (``remount``: unmount
    it first); returns why it isn't connected, or None. The reason is also
    kept for ``last_error``."""
    with _lock(row.id):
        if remount:
            unmount(row.path)
        error = None if is_mounted(row.path) else _mount(row)
        if error:
            _errors[row.id] = error
        else:
            _errors.pop(row.id, None)
        return error


def disconnect(row: MediaSource) -> None:
    """Unmount the share of a removed source and remove its mount point."""
    with _lock(row.id):
        unmount(row.path)
        _errors.pop(row.id, None)
        try:
            os.rmdir(row.path)
        except OSError:
            pass  # never created, or still in use


def last_error(id: int) -> Optional[str]:
    return _errors.get(id)


def connect_all() -> int:
    """Mount every share that isn't mounted; returns how many are connected."""
    with Session(db.engine) as session:
        rows = session.exec(select(MediaSource).where(MediaSource.kind == "smb")).all()
    connected = 0
    for row in rows:
        error = connect(row)
        if error:
            print(f"[SMB] {row.smbShare}: {error}", flush=True)
        else:
            connected += 1
    return connected


async def reconnect_loop():
    """Every few minutes, mount the shares that aren't (e.g. were down at
    startup); a mounted share that went down comes back by itself."""
    print("[Task] SMB reconnect task started", flush=True)
    try:
        while True:
            try:
                await asyncio.to_thread(connect_all)
            except Exception as e:  # keep retrying
                print(f"[Task] SMB reconnect error: {e}", flush=True)
            await asyncio.sleep(RECONNECT_SECONDS)
    except asyncio.CancelledError:
        print("[Task] SMB reconnect task stopped", flush=True)
        raise
