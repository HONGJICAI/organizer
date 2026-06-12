"""Image API endpoints — in-memory store, populated at bootstrap"""
import datetime
import os
import pathlib
import shutil
import threading
from typing import Dict, List

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.security import HTTPAuthorizationCredentials
from core.auth import _bearer, require_auth, require_media_auth
from fastapi_utils.api_model import APIMessage
from fastapi_utils.cbv import cbv
from PIL import Image as PILImage

import global_data
from api.comicpage import PAGE_CACHE_CONTROL, page_etag, resize_to_width
from comicfile import allowImgs, mediaTypes
from core.exceptions import abort
from model import ImageEntity
from schemas.common import FavorResponse, ProgressRequest, ProgressResponse
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
    try:
        names = [
            f for f in os.listdir(folder_path)
            if os.path.isfile(os.path.join(folder_path, f))
            and os.path.splitext(f)[1].lower() in _IMAGE_EXTS
        ]
    except OSError:
        return []
    return sorted(names)


def _gen_cover(entity: ImageEntity, overwrite=False, page=0) -> bool:
    name = f"{entity.id}_0.jpg"
    cover_path = os.path.join(global_data.Config.nginx_image_path, name)
    if overwrite or not os.path.exists(cover_path):
        files = _image_files(entity.path)
        if not files or page >= len(files):
            return False
        try:
            img = PILImage.open(os.path.join(entity.path, files[page]))
            img.thumbnail((300, 300))
            img = img.convert("RGB")
            img.save(cover_path, "JPEG")
            return True
        except Exception as ex:
            print("gen image cover fail:", entity.path, ex)
    return False


def bootstrap():
    """Scan image folders and (re)populate the in-memory store."""
    new_store: Dict[int, ImageEntity] = {}
    id_counter = 0
    for scan_path in global_data.Config.Image.scan_pathes:
        if not os.path.isdir(scan_path):
            continue
        try:
            entries = sorted(os.scandir(scan_path), key=lambda e: e.name)
        except OSError as e:
            print(f"Failed to scan {scan_path}: {e}")
            continue
        for entry in entries:
            if not entry.is_dir(follow_symlinks=False):
                continue
            files = _image_files(entry.path)
            if not files:
                continue
            id_counter += 1
            entity = ImageEntity.from_path(pathlib.Path(entry.path), id_counter)
            entity.page = len(files)
            new_store[id_counter] = entity

    with _store_lock:
        _store.clear()
        _store.update(new_store)

    print(f"[Images] Loaded {len(new_store)} image folder(s) into memory")


def _get(id: int) -> ImageEntity:
    entity = _store.get(id)
    if entity is None:
        abort(404, "Image not found")
    return entity


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
        return ImageDetailResponse(pageDetails=[ImagePageDetailResponse(name=f) for f in files])

    @router.get("/api/images/{id}/{page}", tags=["images"])
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

    @router.post("/api/images/{id}/favor", tags=["images"])
    def favor(self, id: int, _: None = Depends(require_auth)) -> FavorResponse:
        entity = _get(id)
        entity.favorited = True
        return FavorResponse(favorited=True)

    @router.delete("/api/images/{id}/favor", tags=["images"])
    def unfavor(self, id: int, _: None = Depends(require_auth)) -> FavorResponse:
        entity = _get(id)
        entity.favorited = False
        return FavorResponse(favorited=False)

    @router.post("/api/images/{id}/refresh", tags=["images"])
    def refresh(self, id: int, _: None = Depends(require_auth)) -> ImageEntity:
        entity = _get(id)
        refreshed = ImageEntity.from_path(pathlib.Path(entity.path), entity.id)
        entity.page = len(_image_files(entity.path))
        entity.updateTime = refreshed.updateTime
        entity.size = refreshed.size
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
        entity.name = new_name
        entity.path = new_path
        return ImageRenameResponse(name=new_name)

    @router.delete("/api/images/{id}", tags=["images"])
    def delete(self, id: int, _: None = Depends(require_auth)) -> APIMessage:
        entity = _get(id)
        if entity.favorited:
            abort(400, "Cannot delete favorited image folder")
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
        return APIMessage(detail="Deleted")

    @router.post("/api/images/{id}/{page}/cover", tags=["images"])
    def set_cover(self, id: int, page: int, _: None = Depends(require_auth)) -> Response:
        entity = _get(id)
        cover_page = (page - 1) if page > 0 else 0
        if _gen_cover(entity, overwrite=True, page=cover_page):
            entity.coverPosition = page
            return Response(status_code=200)
        abort(500)
