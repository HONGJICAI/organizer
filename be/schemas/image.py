"""Pydantic models for image-related requests and responses"""
from pydantic import BaseModel
from typing import List


class ImagePageDetailResponse(BaseModel):
    name: str


class ImageDetailResponse(BaseModel):
    pageDetails: List[ImagePageDetailResponse]


class ImageRenameRequest(BaseModel):
    name: str


class ImageRenameResponse(BaseModel):
    name: str
