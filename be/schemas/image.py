"""Pydantic models for image-related requests and responses"""
from pydantic import BaseModel, Field
from typing import List


class ImagePageDetailResponse(BaseModel):
    name: str
    size: int = Field(description="Page file size in bytes")


class ImageDetailResponse(BaseModel):
    pageDetails: List[ImagePageDetailResponse]


class ImageRenameRequest(BaseModel):
    name: str


class ImageRenameResponse(BaseModel):
    name: str
