import enum
import hashlib
import os
import time
from concurrent.futures import ThreadPoolExecutor
from typing import List


def str2md5(s: str):
    m = hashlib.md5()
    m.update(s.encode("utf-8"))
    return m.hexdigest()


def create_soft_link(src: str, dst: str):
    if not os.path.exists(dst):
        os.symlink(src, dst)


class PathState(str, enum.Enum):
    """Tri-state result of probing whether a backing file still exists."""

    PRESENT = "present"
    ABSENT = "absent"
    UNKNOWN = "unknown"


def probe_path(path: str, retries: int = 2, backoff: float = 0.1) -> PathState:
    """Classify a path as PRESENT / ABSENT / UNKNOWN.

    ``os.path.exists`` collapses "genuinely gone" (ENOENT) and "transient I/O
    error" (an SMB/NFS share blipping: ESTALE / ETIMEDOUT / host down / ...)
    into the same ``False``. On a network mount that distinction is the whole
    game: confirming — or clearing — a ``missing`` flag on a momentary blip can
    end up deleting a file that is actually fine. So we ``stat`` and read the
    error instead:

    * ``FileNotFoundError`` (ENOENT) -> ``ABSENT`` — but only if the parent
      directory is itself reachable. If the parent can't be stat'd either, the
      whole mount is likely down, so we treat it as ``UNKNOWN`` rather than
      trusting an ENOENT produced by an unmounted share.
    * any other ``OSError`` -> ``UNKNOWN`` (retried with backoff, since these
      are exactly the errors that self-heal once the share recovers).
    """
    for attempt in range(retries + 1):
        try:
            os.stat(path)
            return PathState.PRESENT
        except FileNotFoundError:
            parent = os.path.dirname(path) or "."
            try:
                os.stat(parent)
                # Parent is reachable and the file isn't there: a real deletion.
                return PathState.ABSENT
            except OSError:
                # Parent unreachable too -> the mount is probably gone, not the
                # file. Fall through to the retry/unknown path.
                pass
        except OSError:
            # ESTALE / ETIMEDOUT / EHOSTDOWN / ... — transient, worth retrying.
            pass
        if attempt < retries and backoff > 0:
            time.sleep(backoff * (2 ** attempt))
    return PathState.UNKNOWN


def probe_paths(paths: List[str], max_workers: int = 8) -> List[PathState]:
    """Probe several paths concurrently, preserving input order.

    The probe is a pure ``stat`` with no DB access, so it parallelizes safely;
    fanning out matters because per-file latency on a network mount is the
    dominant cost when re-checking a batch of files.
    """
    if not paths:
        return []
    with ThreadPoolExecutor(max_workers=min(max_workers, len(paths))) as ex:
        return list(ex.map(probe_path, paths))
