"""Image API endpoints — in-memory store, populated at bootstrap.

Image albums are deliberately lightweight: a view over plain folders with no
database rows. Anything worth keeping (favorites, custom covers) belongs to
comics — convert an album to keep it. The store is rebuilt by every scan; a
JSON snapshot of the last scan result only makes the list available right
after a restart instead of empty until the rescan finishes. Reading progress
is in-memory only and is lost on restart.
"""
import datetime
import hashlib
import json
import os
import pathlib
import shutil
import threading
import zipfile
from typing import Dict, List

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.security import HTTPAuthorizationCredentials
from core.auth import _bearer, require_auth, require_media_auth
from fastapi_utils.api_model import APIMessage
from fastapi_utils.cbv import cbv
from sqlmodel import Session, select

import db
import global_data
from api.comicpage import PAGE_CACHE_CONTROL, page_etag, resize_to_width
from comicfile import allowImgs, image_info, mediaTypes, page_sort_key
from core.exceptions import abort
from core.scan_progress import progress
from loader import ComicLoader
from model import ComicEntity, ImageEntity
from schemas.common import PageInfoResponse, ProgressRequest, ProgressResponse
from schemas.image import (
    ImageDetailResponse,
    ImagePageDetailResponse,
    ImageRenameRequest,
    ImageRenameResponse,
)

router = APIRouter()

_IMAGE_EXTS = set(allowImgs)

# In-memory store: {id: ImageEntity}
_store: Dict[int, ImageEntity] = {}
_store_lock = threading.Lock()


def _image_files(folder_path: str) -> List[str]:
    # scandir + DirEntry.is_file() reads d_type from the directory listing,
    # avoiding a stat() per file (listdir + isfile costs one stat each).
    try:
        with os.scandir(folder_path) as it:
            names = [
                e.name for e in it
                if e.is_file()
                and os.path.splitext(e.name)[1].lower() in _IMAGE_EXTS
            ]
    except OSError:
        return []
    return sorted(names, key=page_sort_key)


def _album_id(path: str, taken: Dict[int, ImageEntity]) -> int:
    """Stable id derived from the folder path.

    The same folder gets the same id across scans and restarts, so ids in the
    snapshot, open reader tabs and cover URLs stay valid after a rescan. 48 bits
    keep it within JavaScript's safe-integer range; a (practically impossible)
    collision probes to the next free id.
    """
    digest = hashlib.sha1(path.encode("utf-8", "surrogateescape")).digest()
    id = int.from_bytes(digest[:6], "big") or 1
    while id in taken:
        id += 1
    return id


# Fields persisted in the snapshot: only what a scan (or refresh, for size)
# derives from disk. Per-user state such as reading progress is not saved.
_SNAPSHOT_FIELDS = {"id", "name", "path", "page", "size", "updateTime", "entityUpdateTime"}


def save_snapshot():
    """Write the current store to the snapshot file (atomically).

    Called after a scan and after endpoints that change albums on disk. Failure
    only costs the fast start next time, so it is logged and swallowed.
    """
    path = global_data.Config.image_snapshot_path
    with _store_lock:
        rows = [e.model_dump(mode="json", include=_SNAPSHOT_FIELDS) for e in _store.values()]
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False)
        os.replace(tmp, path)
    except OSError as e:
        print(f"[Images] Failed to write snapshot: {e}")


def load_snapshot() -> int:
    """Fill the store from the last snapshot; returns the number loaded.

    Runs at startup before the background scan so the list is not empty while
    it runs. A missing or unreadable snapshot is ignored (the scan fills the
    store as before), and a store the scan already filled is never overwritten.
    """
    path = global_data.Config.image_snapshot_path
    try:
        with open(path, encoding="utf-8") as f:
            rows = json.load(f)
        entities = [ImageEntity.model_validate(r) for r in rows]
    except FileNotFoundError:
        return 0
    except (OSError, ValueError, TypeError) as e:
        print(f"[Images] Ignoring unreadable snapshot: {e}")
        return 0
    with _store_lock:
        if _store:
            return 0
        _store.update({e.id: e for e in entities})
    print(f"[Images] Loaded {len(entities)} image folder(s) from snapshot")
    return len(entities)


def _leaf_image_dirs(scan_path: str) -> List[str]:
    """Recursively find pure image folders under scan_path.

    A folder qualifies only if it contains nothing but image files — no
    subdirectories and no non-image files. This keeps every collected album
    safe to delete wholesale (it matches the guard in the delete endpoint, so
    deletion never risks touching unrelated files), and a "mixed" folder
    (images plus subfolders) yields its pure leaves rather than itself.
    os.walk does not follow symlinks by default, so symlinked dirs are not
    descended into (avoids loops). Like comics/videos, the album name is the
    folder's basename, not its relative path.
    """
    leaves = []

    def unreadable(err: OSError):
        # os.walk skips folders it can't list; make that visible.
        progress.add_issue("image", "warning", err.filename or scan_path, f"Can't read folder: {err.strerror or err}")

    for root, dirs, files in os.walk(scan_path, onerror=unreadable):
        if dirs:
            continue  # has a subfolder -> not a pure leaf
        exts = [os.path.splitext(f)[1].lower() for f in files]
        if files and all(ext in _IMAGE_EXTS for ext in exts):
            leaves.append(root)
    return sorted(leaves)


def bootstrap():
    """Scan image folders and (re)populate the in-memory store."""
    new_store: Dict[int, ImageEntity] = {}
    for scan_path in global_data.Config.Image.scan_pathes:
        if not os.path.isdir(scan_path):
            progress.add_issue("image", "warning", scan_path, "Scan path not found (not mounted?)")
            continue
        try:
            leaves = _leaf_image_dirs(scan_path)
        except OSError as e:
            print(f"Failed to scan {scan_path}: {e}")
            progress.add_issue("image", "warning", scan_path, f"Can't scan: {e}")
            continue
        for leaf in leaves:
            files = _image_files(leaf)
            if not files:
                continue
            try:
                mtime = datetime.datetime.fromtimestamp(os.stat(leaf).st_mtime)
            except OSError as e:
                # Removed or moved mid-scan: skip it rather than fail the scan.
                progress.add_issue("image", "warning", leaf, f"Folder vanished during scan: {e.strerror or e}")
                continue
            id = _album_id(leaf, new_store)
            # size is not computed here: that means a recursive stat() of every
            # file (see get_dir_size), which makes bootstrap minutes-slow on
            # large/remote folders. The refresh endpoint fills it on demand, and
            # it is carried over below while the folder stays unchanged.
            new_store[id] = ImageEntity(
                id=id,
                size=0,
                name=os.path.basename(leaf),
                path=leaf,
                updateTime=mtime,
                # Cover cache-bust token: tie it to the folder, not the scan,
                # so a rescan doesn't make browsers refetch every cover.
                entityUpdateTime=mtime,
                page=len(files),
            )

    with _store_lock:
        # Keep what the scan cannot cheaply recompute: reading progress, and a
        # refreshed size as long as the folder has not changed since.
        for id, entity in new_store.items():
            old = _store.get(id)
            if old is None or old.path != entity.path:
                continue
            entity.lastViewedPosition = old.lastViewedPosition
            entity.lastViewedTime = old.lastViewedTime
            if old.updateTime == entity.updateTime and old.page == entity.page:
                entity.size = old.size
        _store.clear()
        _store.update(new_store)

    print(f"[Images] Loaded {len(new_store)} image folder(s) into memory")
    save_snapshot()


def _refresh_album(path: str):
    """Update the page count of the album at `path`, if it is in the store.

    Used after a like adds a file to the liked album, so its count is right
    before the next scan. An album not in the store yet (e.g. the liked folder
    was empty at scan time) shows up with the next scan.
    """
    real = os.path.realpath(path)
    with _store_lock:
        album = next((e for e in _store.values() if os.path.realpath(e.path) == real), None)
        if album is None:
            return
        album.page = len(_image_files(album.path))
        album.updateTime = datetime.datetime.fromtimestamp(os.stat(album.path).st_mtime)
        album.entityUpdateTime = album.updateTime
    save_snapshot()


def _get(id: int) -> ImageEntity:
    entity = _store.get(id)
    if entity is None:
        abort(404, "Image not found")
    return entity


def all_entities() -> List[ImageEntity]:
    with _store_lock:
        return list(_store.values())


@cbv(router)
class ImageCBV:
    @router.get("/api/images", tags=["images"])
    def get_all(self, top: int = None, _: None = Depends(require_auth)) -> List[ImageEntity]:
        entities = sorted(_store.values(), key=lambda e: e.updateTime, reverse=True)
        if top is not None:
            entities = entities[:top]
        return [e.model_dump() for e in entities]

    @router.get("/api/images/{id}", tags=["images"])
    def get(self, id: int, _: None = Depends(require_auth)) -> ImageEntity:
        return _get(id).model_dump()

    @router.get("/api/images/{id}/detail", tags=["images"])
    def detail(self, id: int, _: None = Depends(require_auth)) -> ImageDetailResponse:
        entity = _get(id)
        files = _image_files(entity.path)
        return ImageDetailResponse(pageDetails=[
            ImagePageDetailResponse(name=f, size=os.path.getsize(os.path.join(entity.path, f)))
            for f in files
        ])

    @router.get("/api/images/{id}/pages/{page}", tags=["images"])
    def get_page(
        self,
        id: int,
        page: int,
        request: Request,
        width: int | None = Query(default=None, ge=1, le=4096),
        credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
        token: str | None = Query(default=None),
    ) -> Response:
        # page=0 means cover; negative would index from the end of the folder.
        if page < 0:
            abort(404, "Page not found")
        if page != 0:
            require_media_auth(credentials, token)
        entity = _get(id)
        etag = page_etag(id, page, entity.updateTime, width)
        headers = {"cache-control": PAGE_CACHE_CONTROL, "etag": etag}
        if request.headers.get("if-none-match") == etag:
            return Response(status_code=304, headers=headers)
        files = _image_files(entity.path)
        idx = 0 if page == 0 else page - 1
        if idx >= len(files):
            abort(404, "Page not found")
        img_path = os.path.join(entity.path, files[idx])
        try:
            with open(img_path, "rb") as f:
                content = f.read()
        except OSError:
            abort(404, "Image file not found")
        ext = os.path.splitext(files[idx])[1].lower()
        media_type = mediaTypes.get(ext, "image/jpeg")
        # Resizing a GIF would drop animation frames, so serve it untouched.
        if width is not None and ext != ".gif":
            resized = resize_to_width(content, width)
            if resized is not None:
                content, media_type = resized
        return Response(content=content, media_type=media_type, headers=headers)

    @router.get(
        "/api/images/{id}/pages/{page}/info",
        tags=["images"],
        responses={400: {"model": dict}, 404: {"model": dict}},
    )
    def page_info(self, id: int, page: int, _: None = Depends(require_auth)) -> PageInfoResponse:
        """Original size of an album page (see the comic equivalent)."""
        entity = _get(id)
        files = _image_files(entity.path)
        if not 1 <= page <= len(files):
            abort(404, "Page not found")
        try:
            f = open(os.path.join(entity.path, files[page - 1]), "rb")
        except OSError:
            abort(404, "Image file not found")
        with f:
            try:
                info = image_info(f)
            except Exception:  # includes PIL's UnidentifiedImageError (an OSError)
                abort(400, "Page is not a readable image")
        return PageInfoResponse(**info)

    @router.put("/api/images/{id}/progress", tags=["images"])
    def update_progress(
        self, id: int, req: ProgressRequest, _: None = Depends(require_auth)
    ) -> ProgressResponse:
        entity = _get(id)
        if entity.page > 0 and req.position > entity.page:
            abort(400, "Position out of range")
        entity.lastViewedPosition = req.position
        entity.lastViewedTime = datetime.datetime.now()
        return ProgressResponse(
            position=entity.lastViewedPosition, lastViewedTime=entity.lastViewedTime
        )

    @router.post("/api/images/{id}/refresh", tags=["images"])
    def refresh(self, id: int, _: None = Depends(require_auth)) -> ImageEntity:
        entity = _get(id)
        refreshed = ImageEntity.from_path(pathlib.Path(entity.path), entity.id)
        entity.page = len(_image_files(entity.path))
        entity.updateTime = refreshed.updateTime
        entity.size = refreshed.size
        save_snapshot()
        return entity.model_dump()

    @router.post("/api/images/{id}/rename", tags=["images"])
    def rename(self, id: int, req: ImageRenameRequest, _: None = Depends(require_auth)) -> ImageRenameResponse:
        entity = _get(id)
        if not os.path.exists(entity.path):
            abort(404, "Image folder not found in filesystem")
        new_name = req.name
        if new_name == entity.name:
            abort(400, "Name is same")
        new_path = os.path.join(os.path.dirname(entity.path), new_name)
        if os.path.exists(new_path):
            abort(400, "Folder already exists")
        if any(e.name == new_name for e in _store.values() if e.id != id):
            abort(400, "Image folder with same name already exists")
        os.rename(entity.path, new_path)
        # The id stays as is until the next scan re-derives it from the new path.
        entity.name = new_name
        entity.path = new_path
        save_snapshot()
        return ImageRenameResponse(name=new_name)

    @router.delete("/api/images/{id}/pages/{page}", tags=["images"])
    def delete_page(self, id: int, page: int, _: None = Depends(require_auth)) -> ImageEntity:
        """Delete a single image file from an album.

        `page` is 1-based (page 1 == the album's first file), matching get_page.
        Unlike comics (whose pages live inside an archive), image albums are
        plain folders, so an individual file can be removed in place. The page
        count and updateTime are refreshed; bumping updateTime invalidates the
        page etags (including the page-0 cover), since every page after the
        deleted one now maps to a different file.
        """
        if page < 1:
            abort(404, "Page not found")
        entity = _get(id)
        if not os.path.isdir(entity.path):
            abort(404, "Image folder not found in filesystem")
        files = _image_files(entity.path)
        idx = page - 1
        if idx >= len(files):
            abort(404, "Page not found")
        target = files[idx]
        try:
            os.remove(os.path.join(entity.path, target))
        except OSError as e:
            abort(500, f"Cannot delete image: {e}")
        entity.page = len(_image_files(entity.path))
        entity.updateTime = datetime.datetime.now()
        # The cover is page 0 served live, so bump the cover cache-bust token
        # in case the first page is the one that went.
        entity.entityUpdateTime = entity.updateTime
        save_snapshot()
        return entity.model_dump()

    @router.post("/api/images/{id}/pages/{page}/like", tags=["images"])
    def like(self, id: int, page: int, _: None = Depends(require_auth)) -> APIMessage:
        """Copy one page into the liked folder (itself scanned as an album).

        `page` is 1-based. The file is copied byte-for-byte under its own
        extension, like comic page likes, so GIFs stay animated. Liking a page
        of the liked album itself is a no-op.
        """
        if page < 1:
            abort(404, "Page not found")
        entity = _get(id)
        files = _image_files(entity.path)
        if page > len(files):
            abort(404, "Page not found")
        liked_dir = global_data.Config.Image.liked_path
        if os.path.realpath(entity.path) == os.path.realpath(liked_dir):
            return APIMessage(detail="OK")
        src = files[page - 1]
        ext = os.path.splitext(src)[1].lower()
        target = os.path.join(liked_dir, f"{entity.name}_{page}{ext}")
        if os.path.exists(target):
            return APIMessage(detail="OK")
        try:
            os.makedirs(liked_dir, exist_ok=True)
            shutil.copyfile(os.path.join(entity.path, src), target)
        except OSError as e:
            abort(500, f"Cannot like image: {e}")
        _refresh_album(liked_dir)
        return APIMessage(detail="OK")

    @router.delete("/api/images/{id}", tags=["images"])
    def delete(self, id: int, _: None = Depends(require_auth)) -> APIMessage:
        entity = _get(id)
        try:
            entries = list(os.scandir(entity.path))
        except OSError as e:
            abort(500, f"Cannot read folder: {e}")
        non_image = [
            e.name for e in entries
            if e.is_dir() or os.path.splitext(e.name)[1].lower() not in _IMAGE_EXTS
        ]
        if non_image:
            abort(400, f"Folder contains non-image entries: {', '.join(non_image)}")
        shutil.rmtree(entity.path)
        with _store_lock:
            _store.pop(entity.id, None)
        save_snapshot()
        return APIMessage(detail="Deleted")

    @router.post("/api/images/{id}/convert", tags=["images"])
    def convert(self, id: int, _: None = Depends(require_auth)) -> ComicEntity:
        """Package an image folder into a zip comic file and import it.

        The original images are stored verbatim (uncompressed: images are compressed already) under
        their existing filenames, so page order matches what the album shows.
        The source folder is left untouched; the new comic is added to the
        comic library and gets a cover generated like any scanned comic.
        Output goes to COMIC_CONVERT_PATH, or "<first comic scan path>/converted".
        """
        entity = _get(id)
        files = _image_files(entity.path)
        if not files:
            abort(400, "Image folder has no images to convert")

        out_dir = global_data.Config.Comic.convert_path
        if not out_dir:
            scan_pathes = global_data.Config.Comic.scan_pathes
            if not scan_pathes:
                abort(500, "No comic scan path configured")
            out_dir = os.path.join(scan_pathes[0], "converted")
        try:
            os.makedirs(out_dir, exist_ok=True)
        except OSError as e:
            abort(500, f"Cannot create comic directory: {e}")
        out_path = os.path.join(out_dir, f"{entity.name}.zip")

        if os.path.exists(out_path):
            abort(400, "A comic file with this name already exists")
        with Session(db.engine) as session:
            if session.exec(select(ComicEntity).where(ComicEntity.path == out_path)).first():
                abort(400, "A comic with this path already exists")

        try:
            with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_STORED) as zf:
                for fname in files:
                    zf.write(os.path.join(entity.path, fname), arcname=fname)
        except OSError as e:
            # Don't leave a half-written archive behind for the next scan to pick up.
            if os.path.exists(out_path):
                os.remove(out_path)
            abort(500, f"Failed to create comic file: {e}")

        try:
            ComicLoader().load(out_path)
        except Exception as e:
            if os.path.exists(out_path):
                os.remove(out_path)
            abort(400, f"Failed to import comic: {e}")

        with Session(db.engine) as session:
            comic = session.exec(select(ComicEntity).where(ComicEntity.path == out_path)).first()
        if comic is None:
            abort(500, "Comic was created but could not be loaded")
        return comic.model_dump()
