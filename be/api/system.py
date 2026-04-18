"""System health and debug endpoints"""
from typing import Dict
from fastapi import APIRouter
from pydantic import BaseModel

from tasks.cache import comic_access_cache
from tasks.backup import backup_database


router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    cache_size: int
    message: str


@router.get("/api/health", tags=["system"])
def health_check() -> HealthResponse:
    """Health check endpoint with cache info"""
    return HealthResponse(
        status="ok",
        cache_size=len(comic_access_cache),
        message="Application is running"
    )


@router.post("/api/debug/backup-now", tags=["system"])
async def trigger_backup() -> Dict[str, str]:
    """Manually trigger a database backup for testing"""
    try:
        await backup_database()
        return {"status": "success", "message": "Backup completed"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
