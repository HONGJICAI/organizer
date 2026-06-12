"""Common Pydantic models for API responses"""
from datetime import datetime

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
