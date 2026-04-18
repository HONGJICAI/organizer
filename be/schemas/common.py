"""Common Pydantic models for API responses"""
from pydantic import BaseModel


class MessageResponse(BaseModel):
    """Standard message response"""
    msg: str


class FavorResponse(BaseModel):
    """Response for favor/unfavor operations"""
    favorited: bool
