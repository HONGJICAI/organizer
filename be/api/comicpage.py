"""Comic page API endpoints"""
import datetime
import io
import os
from fastapi import APIRouter, Depends, Response
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
from tasks.cache import comic_access_cache


router = APIRouter()


@cbv(router)
class ComicPageCBV:
    session: Session = Depends(db.get_session)

    def __del__(self):
        self.session.close()

    def __get(self, id: int) -> ComicEntity:
        statement = select(ComicEntity).where(ComicEntity.id == id)
        comic = self.session.exec(statement).first()
        if comic is None:
            abort(404, "Comic not found")
        return comic

    @router.get("/api/comics/{id}/{page}", tags=["comicpage"])
    def get(self, id: int, page: int) -> Response:
        comic = self.__get(id)
        cf = comicfile.create_open(comic.path)
        if cf is None:
            abort(404, "Comic file not found")
        ok, bytes = cf.read(page - 1)
        if ok:
            # Record access in cache (dict assignment is atomic)
            comic_access_cache[id] = (datetime.datetime.now(), page)
            
            return Response(
                content=bytes,
                media_type="image/jpeg",
                headers={"cache-control": "max-age=604800"},
            )

        abort(404, "Page not found")

    @router.post("/api/comics/{id}/{page}/like", tags=["comicpage"])
    def like(self, id: int, page: int):
        comic = self.__get(id)
        name = f"{comic.name}_{page}.jpg"
        path = os.path.join(global_data.Config.nginx_image_path, name)
        if not os.path.exists(path):
            cf = comicfile.create_open(comic.path)
            if cf is None:
                abort(404, "Comic file not found")
            ok, bytes = cf.read(page - 1)
            if ok:
                img = Image.open(io.BytesIO(bytes))
                img = img.convert("RGB")
                img.save(path, "JPEG")
                return APIMessage(detail="OK")

        abort(404)

    @router.post("/api/comics/{id}/{page}/cover", tags=["comicpage"])
    def set_cover(self, id: int, page: int):
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
