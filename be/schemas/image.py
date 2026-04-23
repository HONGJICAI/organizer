"""Pydantic models for image-related responses"""
from datetime import datetime
from typing import List
from pydantic import BaseModel


class ImageFileResponse(BaseModel):
    name: str
    url: str


class ImageFolderResponse(BaseModel):
    id: str
    name: str
    path: str
    count: int
    size: int
    updateTime: datetime
    coverUrl: str


class ImageFolderDetailResponse(ImageFolderResponse):
    files: List[ImageFileResponse]
