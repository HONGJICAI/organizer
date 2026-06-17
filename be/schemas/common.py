"""Common Pydantic models for API responses"""
from datetime import datetime
from typing import List

from pydantic import BaseModel, Field


class MessageResponse(BaseModel):
    """Standard message response"""
    msg: str


class ProgressRequest(BaseModel):
    """Request to update reading progress"""
    position: int = Field(ge=1, description="1-based page position")


class ProgressResponse(BaseModel):
    """Response for reading progress update"""
    position: int
    lastViewedTime: datetime


class FavorResponse(BaseModel):
    """Response for favor/unfavor operations"""
    favorited: bool


class CheckRequest(BaseModel):
    """Request to re-verify on disk whether the backing files still exist."""
    ids: List[int] = Field(description="Entity ids to probe")


class CheckResult(BaseModel):
    """Per-id result of a file-existence check.

    ``status`` is one of:
    * ``present``  — file is back on disk; the ``missing`` flag was cleared
    * ``absent``   — file is confirmed gone; the ``missing`` flag was set
    * ``unknown``  — could not be determined (mount blip); flag left untouched
    * ``notfound`` — no such id in the database
    """
    id: int
    status: str


class CheckResponse(BaseModel):
    """Response for a batch file-existence check."""
    results: List[CheckResult]
