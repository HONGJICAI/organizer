"""System health and debug endpoints"""
import os
from datetime import datetime, timedelta
from typing import Dict, List, Literal, Optional
from fastapi import APIRouter
from pydantic import BaseModel, Field

from core.exceptions import abort
from core.jobs import Job, jobs
from core.scan_progress import progress
from covers import regen
from tasks.backup import backup_database


router = APIRouter()

# ---------------------------------------------------------------------------
# Heavy jobs — scans, cover runs and comic moves (mover.py) share core.jobs' single-lane queue; live
# progress stays in core.scan_progress and covers.regen.
# ---------------------------------------------------------------------------


def _run_scan(media_type: str):
    """Scan the requested media, each type in its own phase.

    A failing phase is recorded and the next one still runs, so an unreadable
    image folder doesn't stop comics and videos from being scanned. The result
    is "success", "partial" (some phases failed) or "error" (all did), with
    per-phase outcomes under ``phases`` and the failures joined in ``message``.
    """
    from loader import ComicLoader, VideoLoader
    from api.images import bootstrap as bootstrap_images

    def images():
        progress.set_phase("images", 0)
        bootstrap_images()

    # Images first: bootstrap is cheap (one readdir per folder) and the
    # in-memory store is empty until it runs, while comic/video scans can take
    # a while without leaving the UI empty.
    def comics():
        import mover
        for path in mover.unmounted_paths():
            progress.add_issue(
                "comic", "warning", path,
                "Not on a mounted drive: files here live inside the container and are lost "
                "when it is recreated; moves into it are refused. Mount a volume here (see compose.yaml).",
            )
        ComicLoader().work()

    phases = [
        ("images", "image", images),
        ("comics", "comic", comics),
        ("videos", "video", lambda: VideoLoader().work()),
    ]
    results, errors = {}, {}
    for name, media, run in phases:
        if media_type not in (name, "all"):
            continue
        try:
            run()
            results[name] = "done"
        except Exception as e:
            reason = str(e) or type(e).__name__
            results[name] = "error"
            errors[name] = reason
            progress.add_issue(media, "error", "", f"{name} scan failed: {reason}")
    if not errors:
        progress.finish({"status": "success", "phases": results})
        return
    progress.finish({
        "status": "partial" if len(errors) < len(results) else "error",
        "phases": results,
        "message": "; ".join(f"{name}: {reason}" for name, reason in errors.items()),
    })


def _scan_job(job: Job):
    media_type = job.params["media_type"]
    progress.start(media_type)
    _run_scan(media_type)
    result = progress.last_result or {}
    if result.get("status") in ("error", "partial"):
        raise RuntimeError(result.get("message") or "Scan failed")


def _covers_job(job: Job):
    regen.run(job.params["mode"])


def _scan_subsumes(a: Dict[str, str], b: Dict[str, str]) -> bool:
    # A full scan covers any single media type.
    return a["media_type"] in ("all", b["media_type"])


def _covers_subsumes(a: Dict[str, str], b: Dict[str, str]) -> bool:
    # Rewriting every cover also writes the missing ones.
    return a["mode"] in ("all", b["mode"])


jobs.register("scan", _scan_job, subsumes=_scan_subsumes)
jobs.register("covers", _covers_job, cancel=regen.cancel, subsumes=_covers_subsumes)


def start_scan(media_type: str) -> str:
    """Queue a scan: ``"started"``, ``"queued"`` behind another job, or
    ``"already_queued"`` when the same scan is already waiting.

    Shared by the HTTP endpoint, the startup scan and the daily scan, so scans
    never overlap each other or a cover run.
    """
    return jobs.submit("scan", {"media_type": media_type})[1]


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    status: str
    message: str


class ScanResponse(BaseModel):
    status: Literal["started", "queued", "already_queued"]
    message: str


class SlowFile(BaseModel):
    path: str
    ms: float


class ScanTiming(BaseModel):
    count: int
    avg_ms: float
    p95_ms: float
    slowest: List[SlowFile]


class ScanIssue(BaseModel):
    media: Literal["comic", "video", "image"]
    level: Literal["skipped", "warning", "error"] = Field(
        description="skipped: found but not imported; warning: scanned, but something's off; error: a phase failed"
    )
    path: str = Field(description="File or folder concerned; empty for a whole-phase error")
    reason: str


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
    issue_count: int = Field(default=0, description="Problems the scan ran into, all levels")
    issues: List[ScanIssue] = Field(default_factory=list, description="First issues only; `issue_count` counts all")


class DailyScanInfo(BaseModel):
    scan_hour: int
    next_run: str


class BackupInfo(BaseModel):
    last_backup: Optional[str] = None
    backup_count: int = 0
    cadence_hours: int = 24


class CoverFailure(BaseModel):
    id: int
    name: str
    reason: str


class CoverRegenStatus(BaseModel):
    running: bool
    cancelled: bool = Field(default=False, description="The last run was cancelled before finishing")
    mode: Optional[Literal["all", "missing"]] = None
    total: int
    processed: int
    failed: int
    failures: List[CoverFailure] = Field(description="First failures only; `failed` counts all")
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


QueueStatus = Literal["started", "queued", "already_queued"]


class CoverRegenResponse(BaseModel):
    status: QueueStatus
    message: str


class JobInfo(BaseModel):
    id: int
    kind: Literal["scan", "covers", "move"]
    params: Dict[str, str]
    state: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    error: Optional[str] = None
    cancellable: bool


class JobsResponse(BaseModel):
    """The heavy-job queue: what runs now, what waits, what ran recently"""
    running: Optional[JobInfo] = None
    queued: List[JobInfo]
    history: List[JobInfo] = Field(description="Most recent first")


class JobCancelResponse(BaseModel):
    status: Literal["cancelled", "cancelling"]


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
    """Queue a background scan to import new media files into the database."""
    status = start_scan(media_type)
    return ScanResponse(status=status, message=_queue_message(status, f"Scan ({media_type})"))


@router.get("/api/system/scan", tags=["system"])
def scan_status() -> ScanStatusResponse:
    """Live progress + metrics for the running scan (or the most recent one)."""
    return ScanStatusResponse(**progress.snapshot())


@router.post("/api/system/covers", tags=["system"])
def regenerate_covers(mode: Literal["all", "missing"] = "all") -> CoverRegenResponse:
    """Queue a cover run: every live comic's cover, or only those without a cover file."""
    _, status = jobs.submit("covers", {"mode": mode})
    what = "Missing cover generation" if mode == "missing" else "Cover regeneration"
    return CoverRegenResponse(status=status, message=_queue_message(status, what))


@router.get("/api/system/covers", tags=["system"])
def cover_regen_status() -> CoverRegenStatus:
    """Progress of the running (or most recent) cover regeneration."""
    return CoverRegenStatus(**regen.snapshot())


def _queue_message(status: str, what: str) -> str:
    return {
        "started": f"{what} started",
        "queued": f"{what} queued behind the running job",
        "already_queued": f"{what} is already covered by a job waiting in the queue",
    }[status]


def _job_info(job: Job) -> JobInfo:
    return JobInfo(
        id=job.id, kind=job.kind, params=job.params, state=job.state,
        created_at=job.created_at, started_at=job.started_at, finished_at=job.finished_at,
        error=job.error, cancellable=jobs.cancellable(job),
    )


@router.get("/api/system/jobs", tags=["system"])
def list_jobs() -> JobsResponse:
    """The running heavy job (scan, cover run or comic move), the queue behind it, and recent history."""
    snap = jobs.snapshot()
    return JobsResponse(
        running=_job_info(snap["running"]) if snap["running"] else None,
        queued=[_job_info(j) for j in snap["queued"]],
        history=[_job_info(j) for j in snap["history"]],
    )


@router.delete(
    "/api/system/jobs/{id}",
    tags=["system"],
    responses={400: {"model": dict}, 404: {"model": dict}},
)
def cancel_job(id: int) -> JobCancelResponse:
    """Cancel a queued job, or ask a running cover run to stop. Running scans can't be cancelled."""
    result = jobs.cancel(id)
    if result is None:
        abort(404, "No queued or running job with that id")
    if result == "not_cancellable":
        abort(400, "This job can't be cancelled while it runs")
    return JobCancelResponse(status=result)


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
