"""Comic page API endpoints"""
import datetime
import io
import os
from fastapi import APIRouter, Depends, Query, Request, Response
from core.auth import require_auth, require_media_auth
from fastapi_utils.api_model import APIMessage
from fastapi_utils.cbv import cbv
from PIL import Image
from sqlmodel import Session, select

import comicfile
import db
import global_data
from core.exceptions import abort
from loader import ComicLoader
from model import ComicEntity
from schemas.common import ProgressRequest, ProgressResponse


router = APIRouter()

PAGE_CACHE_CONTROL = "max-age=604800"


def page_etag(entity_id: int, page: int, updateTime: datetime.datetime, width: int | None) -> str:
    return f'"{entity_id}-{page}-{int(updateTime.timestamp())}-{width or 0}"'


def resize_to_width(buf: bytes, width: int) -> tuple[bytes, str] | None:
    """Downscale image bytes to the given width (keeps aspect ratio, returns WebP).

    Returns None when the image is already narrow enough or cannot be decoded.
    """
    try:
        img = Image.open(io.BytesIO(buf))
    except Exception:
        return None
    if img.width <= width:
        return None
    img.thumbnail((width, img.height * width // img.width))
    if img.mode != "RGBA":
        img = img.convert("RGB")
    out = io.BytesIO()
    # method=0 favors encode speed; still far smaller than JPEG for comic pages.
    img.save(out, "WEBP", quality=80, method=0)
    return out.getvalue(), "image/webp"


@cbv(router)
class ComicPageCBV:
    session: Session = Depends(db.get_session)

    def __get(self, id: int) -> ComicEntity:
        statement = select(ComicEntity).where(ComicEntity.id == id)
        comic = self.session.exec(statement).first()
        if comic is None:
            abort(404, "Comic not found")
        return comic

    @router.get("/api/comics/{id}/pages/{page}", tags=["comicpage"])
    def get(
        self,
        id: int,
        page: int,
        request: Request,
        width: int | None = Query(default=None, ge=1, le=4096),
        _: None = Depends(require_media_auth),
    ) -> Response:
        # Reject 0/negative early: page - 1 would otherwise index from the end.
        if page < 1:
            abort(404, "Page not found")
        comic = self.__get(id)
        etag = page_etag(id, page, comic.updateTime, width)
        headers = {"cache-control": PAGE_CACHE_CONTROL, "etag": etag}
        if request.headers.get("if-none-match") == etag:
            return Response(status_code=304, headers=headers)
        cf = comicfile.create_open(comic.path)
        if cf is None:
            abort(404, "Comic file not found")
        ok, buf = cf.read(page - 1)
        if not ok:
            abort(404, "Page not found")
        ext = os.path.splitext(cf.namelist[page - 1])[1].lower()
        media_type = comicfile.mediaTypes.get(ext, "image/jpeg")
        # Resizing a GIF would drop animation frames, so serve it untouched.
        if width is not None and ext != ".gif":
            resized = resize_to_width(buf, width)
            if resized is not None:
                buf, media_type = resized
        return Response(content=buf, media_type=media_type, headers=headers)

    @router.put("/api/comics/{id}/progress", tags=["comicpage"])
    def update_progress(
        self, id: int, req: ProgressRequest, _: None = Depends(require_auth)
    ) -> ProgressResponse:
        comic = self.__get(id)
        if comic.page > 0 and req.position > comic.page:
            abort(400, "Position out of range")
        comic.lastViewedPosition = req.position
        comic.lastViewedTime = datetime.datetime.now()
        self.session.add(comic)
        self.session.commit()
        return ProgressResponse(
            position=comic.lastViewedPosition, lastViewedTime=comic.lastViewedTime
        )

    @router.post("/api/comics/{id}/pages/{page}/like", tags=["comicpage"])
    def like(self, id: int, page: int, _: None = Depends(require_auth)):
        if page < 1:
            abort(404, "Page not found")
        comic = self.__get(id)
        name = f"{comic.name}_{page}.jpg"
        path = os.path.join(global_data.Config.Image.liked_path, name)
        if os.path.exists(path):
            return APIMessage(detail="OK")
        cf = comicfile.create_open(comic.path)
        if cf is None:
            abort(404, "Comic file not found")
        ok, buf = cf.read(page - 1)
        if not ok:
            abort(404, "Page not found")
        os.makedirs(global_data.Config.Image.liked_path, exist_ok=True)
        img = Image.open(io.BytesIO(buf))
        img = img.convert("RGB")
        img.save(path, "JPEG")
        return APIMessage(detail="OK")

    @router.post("/api/comics/{id}/pages/{page}/cover", tags=["comicpage"])
    def set_cover(self, id: int, page: int, _: None = Depends(require_auth)):
        comic = self.__get(id)
        cf = comicfile.create_open(comic.path)
        if cf is None:
            abort(404, "Comic file not found")
        if ComicLoader.gen_comic_cover(comic, cf, True, page - 1 if page > 0 else 0):
            rsp = Response(status_code=200)
            comic.coverPosition = page
            self.session.add(comic)
            self.session.commit()
            return rsp

        abort(500)
