"""System health and debug endpoints"""
import threading
from typing import Dict, Literal, Optional
from fastapi import APIRouter
from pydantic import BaseModel

from tasks.backup import backup_database


router = APIRouter()

# ---------------------------------------------------------------------------
# Scan state — shared across requests, protected by a lock
# ---------------------------------------------------------------------------

_scan_lock = threading.Lock()
_scan_status: dict = {"running": False, "last_result": None}


def _run_scan(media_type: str):
    from loader import ComicLoader, VideoLoader
    from api.images import bootstrap as bootstrap_images

    results = {}
    try:
        # Images first: bootstrap is cheap (one readdir per folder) and the
        # in-memory store is empty until it runs, while comic/video scans can
        # take a while without leaving the UI empty.
        if media_type in ("images", "all"):
            bootstrap_images()
            results["images"] = "done"
        if media_type in ("comics", "all"):
            ComicLoader().work()
            results["comics"] = "done"
        if media_type in ("videos", "all"):
            VideoLoader().work()
            results["videos"] = "done"
        _scan_status["last_result"] = {"status": "success", **results}
    except Exception as e:
        _scan_status["last_result"] = {"status": "error", "message": str(e)}
    finally:
        _scan_status["running"] = False


def start_scan(media_type: str) -> bool:
    """Launch a background scan unless one is already running.

    Returns True if a scan was started, False if one was already in progress.
    Shared by the HTTP endpoint, the startup scan, and the daily scheduled scan
    so they all go through the same lock and never run concurrently.
    """
    with _scan_lock:
        if _scan_status["running"]:
            return False
        _scan_status["running"] = True

    threading.Thread(target=_run_scan, args=(media_type,), daemon=True).start()
    return True


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    status: str
    message: str


class ScanResponse(BaseModel):
    status: str
    message: str


class ScanStatusResponse(BaseModel):
    running: bool
    last_result: Optional[dict] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/api/health", tags=["system"])
def health_check() -> HealthResponse:
    return HealthResponse(
        status="ok",
        message="Application is running",
    )


@router.post("/api/system/scan", tags=["system"])
def trigger_scan(
    media_type: Literal["comics", "videos", "images", "all"] = "all",
) -> ScanResponse:
    """Start a background scan to import new media files into the database."""
    if not start_scan(media_type):
        return ScanResponse(status="already_running", message="A scan is already in progress")
    return ScanResponse(status="started", message=f"Scan started for: {media_type}")


@router.get("/api/system/scan", tags=["system"])
def scan_status() -> ScanStatusResponse:
    """Check whether a scan is currently running and the result of the last scan."""
    return ScanStatusResponse(
        running=_scan_status["running"],
        last_result=_scan_status["last_result"],
    )


@router.post("/api/debug/backup-now", tags=["system"])
async def trigger_backup() -> Dict[str, str]:
    try:
        await backup_database()
        return {"status": "success", "message": "Backup completed"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
