"""Media sources: the scan folders of each media type (see sources.py), and
SMB shares the app mounts itself (see smb.py)."""
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlmodel import Session

import db
import smb
import sources
from core.exceptions import abort
from model import MediaSource

router = APIRouter()

Media = Literal["comic", "video", "image"]
QueueStatus = Literal["started", "queued", "already_queued"]


class SmbInfo(BaseModel):
    share: str = Field(description="//server/share[/folder]")
    username: Optional[str] = Field(default=None, description="None: guest access")
    domain: Optional[str] = None
    options: Optional[str] = Field(default=None, description="Extra mount.cifs options, comma-separated")
    hasPassword: bool = Field(description="A password is saved; it is never sent back")


class MediaSourceInfo(BaseModel):
    id: Optional[int] = Field(default=None, description="Set on added sources; built-in ones have none")
    media: Media
    kind: Literal["local", "smb"] = "local"
    path: str = Field(description="Where it is scanned; for an SMB share, its mount point")
    builtin: bool = Field(description="From the environment (compose.yaml): always scanned, can't be removed here")
    status: Literal["ok", "not_found", "not_mounted", "not_connected"] = Field(
        description="not_found: the folder is missing (an unmounted drive?); "
        "not_mounted: it is in the container's own filesystem, not on a mounted drive; "
        "not_connected: an SMB share that isn't mounted (see error)"
    )
    error: Optional[str] = Field(default=None, description="Why an SMB share isn't connected, when known")
    smb: Optional[SmbInfo] = Field(default=None, description="Set on SMB shares")


class SmbRequest(BaseModel):
    share: str = Field(description=r"//server/share[/folder] or \\server\share[\folder]")
    username: Optional[str] = Field(default=None, description="Empty: guest access")
    password: Optional[str] = Field(default=None, description="When editing, empty keeps the saved one")
    domain: Optional[str] = None
    options: Optional[str] = Field(default=None, description="Extra mount.cifs options, e.g. vers=2.0")


class MediaSourceRequest(BaseModel):
    media: Media
    kind: Literal["local", "smb"] = "local"
    path: Optional[str] = Field(
        default=None, description="Local folders: absolute folder path as the server (container) sees it"
    )
    smb: Optional[SmbRequest] = Field(default=None, description="SMB shares: how to connect")


class MediaSourceAddResponse(BaseModel):
    source: MediaSourceInfo
    scan: QueueStatus = Field(description="The scan of that media type queued to pick the folder up")


class MediaSourceRemoveResponse(BaseModel):
    scan: QueueStatus = Field(description="The scan of that media type queued to flag its records missing")


class SmbSupport(BaseModel):
    supported: bool
    reason: Optional[str] = Field(default=None, description="Why shares can't be mounted here")


class FolderEntry(BaseModel):
    name: str
    path: str
    mount: bool = Field(description="A mount point: a drive or share mounted into the container")


class FolderListing(BaseModel):
    path: str
    parent: Optional[str] = Field(default=None, description="None at the filesystem root")
    dirs: List[FolderEntry] = Field(description="Subfolders, hidden ones left out")


def _info(source: sources.Source) -> MediaSourceInfo:
    status = sources.status(source)
    info = MediaSourceInfo(
        id=source.id, media=source.media, kind=source.kind, path=source.path,
        builtin=source.builtin, status=status,
    )
    if source.kind == "smb":
        row = source.row
        info.smb = SmbInfo(
            share=row.smbShare, username=row.smbUsername, domain=row.smbDomain,
            options=row.smbOptions, hasPassword=bool(row.smbPassword),
        )
        if status != "ok":
            info.error = smb.last_error(row.id) or "Not connected yet"
    return info


def _row_info(row: MediaSource) -> MediaSourceInfo:
    return _info(sources.Source(
        media=row.media, path=row.path, builtin=False, id=row.id, kind=row.kind, row=row,
    ))


def _scan(media: str) -> str:
    import api.system
    return api.system.start_scan(sources.SCAN_TYPE[media])


def _settings(req: SmbRequest) -> sources.SmbSettings:
    return sources.SmbSettings(
        share=req.share, username=req.username, password=req.password,
        domain=req.domain, options=req.options,
    )


def _smb_row(session: Session, id: int) -> MediaSource:
    row = session.get(MediaSource, id)
    if row is None:
        abort(404, "No added media source with that id")
    if row.kind != "smb":
        abort(400, "Not an SMB share")
    return row


@router.get("/api/system/sources", tags=["system"])
def list_media_sources() -> List[MediaSourceInfo]:
    """Scan folders by media type: built-in ones first, then added ones."""
    return [_info(s) for s in sources.all_sources()]


@router.post("/api/system/sources", tags=["system"], responses={400: {"model": dict}})
def add_media_source(req: MediaSourceRequest, session: Session = Depends(db.get_session)) -> MediaSourceAddResponse:
    """Add a scan folder or SMB share and queue a scan of its media type.

    A local folder must exist in the container (on a mounted drive). An SMB
    share is mounted right away and refused when that fails. Neither may
    overlap another source, of any media type.
    """
    try:
        if req.kind == "smb":
            if req.smb is None:
                abort(400, "SMB settings are missing")
            row = sources.add_smb(session, req.media, _settings(req.smb))
        else:
            row = sources.add(session, req.media, req.path or "")
    except sources.SourceError as e:
        abort(400, str(e))
    return MediaSourceAddResponse(source=_row_info(row), scan=_scan(row.media))


@router.patch(
    "/api/system/sources/{id}", tags=["system"], responses={400: {"model": dict}, 404: {"model": dict}}
)
def update_media_source(id: int, req: SmbRequest, session: Session = Depends(db.get_session)) -> MediaSourceInfo:
    """Change an SMB share's settings; it is remounted with them. When that
    fails, the old settings stay and the reason comes back as a 400."""
    row = _smb_row(session, id)
    try:
        row = sources.update_smb(session, row, _settings(req))
    except sources.SourceError as e:
        abort(400, str(e))
    return _row_info(row)


@router.post(
    "/api/system/sources/{id}/connect", tags=["system"], responses={400: {"model": dict}, 404: {"model": dict}}
)
def connect_media_source(id: int, session: Session = Depends(db.get_session)) -> MediaSourceInfo:
    """Unmount and mount an SMB share again; the result says whether it is
    connected now, and if not, why."""
    row = _smb_row(session, id)
    smb.connect(row, remount=True)
    return _row_info(row)


@router.delete("/api/system/sources/{id}", tags=["system"], responses={404: {"model": dict}})
def remove_media_source(id: int, session: Session = Depends(db.get_session)) -> MediaSourceRemoveResponse:
    """Stop scanning an added source (an SMB share is unmounted). Nothing on
    the drive or share changes; the scan queued here flags its comics and
    videos missing (Cleanup -> Missing files) and drops its image albums."""
    row = session.get(MediaSource, id)
    if row is None:
        abort(404, "No added media source with that id")
    media = row.media
    sources.remove(session, row)
    return MediaSourceRemoveResponse(scan=_scan(media))


@router.get("/api/system/smb", tags=["system"])
def smb_support() -> SmbSupport:
    """Whether SMB shares can be mounted here (mount.cifs installed)."""
    reason = smb.unsupported()
    return SmbSupport(supported=reason is None, reason=reason)


@router.get("/api/system/folders", tags=["system"], responses={400: {"model": dict}})
def list_folders(path: Optional[str] = None) -> FolderListing:
    """The subfolders of ``path`` on the server, for picking a folder to add;
    without ``path``, those of the container's media folder (/data)."""
    try:
        return FolderListing(**sources.browse(path or sources.default_browse_root()))
    except sources.SourceError as e:
        abort(400, str(e))
