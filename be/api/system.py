"""System health and debug endpoints"""
import os
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Literal, Optional
from fastapi import APIRouter
from pydantic import BaseModel

from core.scan_progress import progress
from tasks.backup import backup_database


router = APIRouter()

# ---------------------------------------------------------------------------
# Scan state — live progress lives in core.scan_progress; this lock only
# guards the "is a scan already running" gate so concurrent triggers serialize.
# ---------------------------------------------------------------------------

_scan_lock = threading.Lock()


def _run_scan(media_type: str):
    from loader import ComicLoader, VideoLoader
    from api.images import bootstrap as bootstrap_images

    results = {}
    try:
        # Images first: bootstrap is cheap (one readdir per folder) and the
        # in-memory store is empty until it runs, while comic/video scans can
        # take a while without leaving the UI empty.
        if media_type in ("images", "all"):
            progress.set_phase("images", 0)
            bootstrap_images()
            results["images"] = "done"
        if media_type in ("comics", "all"):
            ComicLoader().work()
            results["comics"] = "done"
        if media_type in ("videos", "all"):
            VideoLoader().work()
            results["videos"] = "done"
        progress.finish({"status": "success", **results})
    except Exception as e:
        progress.finish({"status": "error", "message": str(e)})


def start_scan(media_type: str) -> bool:
    """Launch a background scan unless one is already running.

    Returns True if a scan was started, False if one was already in progress.
    Shared by the HTTP endpoint, the startup scan, and the daily scheduled scan
    so they all go through the same lock and never run concurrently.
    """
    with _scan_lock:
        if progress.running:
            return False
        progress.start(media_type)

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


class SlowFile(BaseModel):
    path: str
    ms: float


class ScanTiming(BaseModel):
    count: int
    avg_ms: float
    p95_ms: float
    slowest: List[SlowFile]


class ScanStatusResponse(BaseModel):
    running: bool
    media_type: Optional[str] = None
    phase: Optional[str] = None
    total: int = 0
    processed: int = 0
    reconciled: int = 0
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    duration_seconds: Optional[float] = None
    timing: ScanTiming
    last_result: Optional[dict] = None


class DailyScanInfo(BaseModel):
    scan_hour: int
    next_run: str


class BackupInfo(BaseModel):
    last_backup: Optional[str] = None
    backup_count: int = 0
    cadence_hours: int = 24


class TasksResponse(BaseModel):
    daily_scan: DailyScanInfo
    backup: BackupInfo


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
    """Live progress + metrics for the running scan (or the most recent one)."""
    return ScanStatusResponse(**progress.snapshot())


@router.get("/api/system/tasks", tags=["system"])
def tasks_status() -> TasksResponse:
    """Background task health: next scheduled scan and database backup state."""
    from tasks.scan import SCAN_HOUR, _seconds_until
    from tasks.backup import _get_paths

    next_run = datetime.now() + timedelta(seconds=_seconds_until(SCAN_HOUR))

    db_path, backup_dir = _get_paths()
    db_stem = os.path.splitext(os.path.basename(db_path))[0]
    backup_ext = os.path.splitext(db_path)[1] or ".db"
    last_backup = None
    backup_count = 0
    if os.path.isdir(backup_dir):
        backups = [
            os.path.join(backup_dir, f)
            for f in os.listdir(backup_dir)
            if f.startswith(f"{db_stem}_") and f.endswith(backup_ext)
        ]
        backup_count = len(backups)
        if backups:
            latest = max(backups, key=os.path.getmtime)
            last_backup = datetime.fromtimestamp(os.path.getmtime(latest)).isoformat()

    return TasksResponse(
        daily_scan=DailyScanInfo(scan_hour=SCAN_HOUR, next_run=next_run.isoformat()),
        backup=BackupInfo(last_backup=last_backup, backup_count=backup_count),
    )


@router.post("/api/debug/backup-now", tags=["system"])
async def trigger_backup() -> Dict[str, str]:
    try:
        await backup_database()
        return {"status": "success", "message": "Backup completed"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
