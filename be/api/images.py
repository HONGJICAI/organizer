"""Image API endpoints — folder-as-unit, all in-memory, no DB"""
import os
from datetime import datetime
from fastapi import APIRouter, HTTPException
from fastapi_utils.cbv import cbv
from typing import List

import global_data
from comicfile import allowImgs
from schemas.image import ImageFileResponse, ImageFolderDetailResponse, ImageFolderResponse
from util import create_soft_link

router = APIRouter()

_IMAGE_EXTS = set(allowImgs)


def _scan_folders() -> List[str]:
    """Return immediate subdirectories of each scan path."""
    folders = []
    for scan_path in global_data.Config.Image.scan_pathes:
        if not os.path.isdir(scan_path):
            continue
        for entry in os.scandir(scan_path):
            if entry.is_dir(follow_symlinks=False):
                folders.append(entry.path)
    return folders


def _image_files(folder_path: str) -> List[str]:
    """Return sorted list of image filenames inside a folder."""
    try:
        names = [
            f for f in os.listdir(folder_path)
            if os.path.isfile(os.path.join(folder_path, f))
            and os.path.splitext(f)[1].lower() in _IMAGE_EXTS
        ]
    except OSError:
        return []
    return sorted(names)


def _ensure_symlink(folder_name: str, folder_path: str):
    """Create nginx symlink so images are served statically."""
    link = os.path.join(global_data.Config.nginx_image_path, folder_name)
    create_soft_link(folder_path, link)


def _folder_to_response(folder_path: str) -> ImageFolderResponse | None:
    folder_name = os.path.basename(folder_path)
    files = _image_files(folder_path)
    if not files:
        return None

    _ensure_symlink(folder_name, folder_path)

    try:
        stat = os.stat(folder_path)
        update_time = datetime.fromtimestamp(stat.st_mtime)
        size = sum(
            os.path.getsize(os.path.join(folder_path, f))
            for f in files
        )
    except OSError:
        return None

    cover_url = f"/images/{folder_name}/{files[0]}"

    return ImageFolderResponse(
        id=folder_name,
        name=folder_name,
        path=folder_path,
        count=len(files),
        size=size,
        updateTime=update_time,
        coverUrl=cover_url,
    )


@cbv(router)
class ImageCBV:
    @router.get("/api/images", tags=["images"])
    def get_all(self) -> List[ImageFolderResponse]:
        results = []
        for folder_path in _scan_folders():
            resp = _folder_to_response(folder_path)
            if resp is not None:
                results.append(resp)
        results.sort(key=lambda r: r.updateTime, reverse=True)
        return results

    @router.get("/api/images/{folder_id}", tags=["images"])
    def get_folder(self, folder_id: str) -> ImageFolderDetailResponse:
        for folder_path in _scan_folders():
            if os.path.basename(folder_path) == folder_id:
                base = _folder_to_response(folder_path)
                if base is None:
                    raise HTTPException(status_code=404, detail="Folder is empty or unreadable")
                files = [
                    ImageFileResponse(
                        name=f,
                        url=f"/images/{folder_id}/{f}",
                    )
                    for f in _image_files(folder_path)
                ]
                return ImageFolderDetailResponse(**base.model_dump(), files=files)
        raise HTTPException(status_code=404, detail="Folder not found")
