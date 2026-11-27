"""Media sources: the scan folders of each media type (see sources.py)."""
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlmodel import Session

import db
import sources
from core.exceptions import abort
from model import MediaSource

router = APIRouter()

Media = Literal["comic", "video", "image"]
QueueStatus = Literal["started", "queued", "already_queued"]


class MediaSourceInfo(BaseModel):
    id: Optional[int] = Field(default=None, description="Set on added folders; built-in ones have none")
    media: Media
    path: str
    builtin: bool = Field(description="From the environment (compose.yaml): always scanned, can't be removed here")
    status: Literal["ok", "not_found", "not_mounted"] = Field(
        description="not_found: the folder is missing (an unmounted drive?); "
        "not_mounted: it is in the container's own filesystem, not on a mounted drive"
    )


class MediaSourceRequest(BaseModel):
    media: Media
    path: str = Field(description="Absolute folder path as the server (container) sees it")


class MediaSourceAddResponse(BaseModel):
    source: MediaSourceInfo
    scan: QueueStatus = Field(description="The scan of that media type queued to pick the folder up")


class MediaSourceRemoveResponse(BaseModel):
    scan: QueueStatus = Field(description="The scan of that media type queued to flag its records missing")


class FolderEntry(BaseModel):
    name: str
    path: str
    mount: bool = Field(description="A mount point: a drive or share mounted into the container")


class FolderListing(BaseModel):
    path: str
    parent: Optional[str] = Field(default=None, description="None at the filesystem root")
    dirs: List[FolderEntry] = Field(description="Subfolders, hidden ones left out")


def _info(source: sources.Source) -> MediaSourceInfo:
    return MediaSourceInfo(
        id=source.id, media=source.media, path=source.path,
        builtin=source.builtin, status=sources.status(source.path),
    )


def _scan(media: str) -> str:
    import api.system
    return api.system.start_scan(sources.SCAN_TYPE[media])


@router.get("/api/system/sources", tags=["system"])
def list_media_sources() -> List[MediaSourceInfo]:
    """Scan folders by media type: built-in ones first, then added ones."""
    return [_info(s) for s in sources.all_sources()]


@router.post("/api/system/sources", tags=["system"], responses={400: {"model": dict}})
def add_media_source(req: MediaSourceRequest, session: Session = Depends(db.get_session)) -> MediaSourceAddResponse:
    """Add a scan folder and queue a scan of its media type.

    The folder must exist in the container (on a mounted drive) and must not
    overlap any other scan folder, of any media type.
    """
    try:
        row = sources.add(session, req.media, req.path)
    except sources.SourceError as e:
        abort(400, str(e))
    source = sources.Source(media=row.media, path=row.path, builtin=False, id=row.id)
    return MediaSourceAddResponse(source=_info(source), scan=_scan(row.media))


@router.delete("/api/system/sources/{id}", tags=["system"], responses={404: {"model": dict}})
def remove_media_source(id: int, session: Session = Depends(db.get_session)) -> MediaSourceRemoveResponse:
    """Stop scanning an added folder. Nothing on disk changes; the scan queued
    here flags its comics and videos missing (Cleanup -> Missing files) and
    drops its image albums."""
    row = session.get(MediaSource, id)
    if row is None:
        abort(404, "No added media source with that id")
    media = row.media
    session.delete(row)
    session.commit()
    return MediaSourceRemoveResponse(scan=_scan(media))


@router.get("/api/system/folders", tags=["system"], responses={400: {"model": dict}})
def list_folders(path: Optional[str] = None) -> FolderListing:
    """The subfolders of ``path`` on the server, for picking a folder to add;
    without ``path``, those of the container's media folder (/data)."""
    try:
        return FolderListing(**sources.browse(path or sources.default_browse_root()))
    except sources.SourceError as e:
        abort(400, str(e))
