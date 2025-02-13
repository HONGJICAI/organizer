import re
import shutil
import threading

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Response
from pydantic import BaseModel
import global_data
import datetime
import io
import pathlib
import db
from typing import Dict, List
import os
from PIL import Image
from sqlmodel import SQLModel, Session, or_, select
from rich.traceback import install
from rich.progress import track
from loader import ComicLoader, VideoLoader

from fastapi_utils.api_model import APIMessage
from fastapi_utils.cbv import cbv

import util
from model import (
    ComicEntity,
    FileEntity,
    VideoEntity,
)
import comicfile

install(show_locals=True)

app = FastAPI()
router = APIRouter()

from fastapi.middleware.cors import CORSMiddleware

origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def abort(code: int, message: str = None):
    raise HTTPException(status_code=code, detail=message)


@cbv(router)
class VideoCBV:
    session: Session = Depends(db.get_session)

    @router.get("/api/videos")
    def get_all(self) -> List[VideoEntity]:
        statement = select(VideoEntity)
        video_entities = self.session.exec(statement).all()

        return [v.model_dump() for v in video_entities]

    def __get(self, id: int) -> VideoEntity:
        statement = select(VideoEntity).where(VideoEntity.id == id)
        video_entity = self.session.exec(statement).first()
        if video_entity is None:
            abort(404, "Video not found")
        return video_entity

    @router.get("/api/videos/{id}")
    def get(self, id: int) -> VideoEntity:
        video_entity = self.__get(id)
        new_name = str(id)
        new_path = os.path.join(global_data.Config.nginx_video_path, new_name)
        util.create_soft_link(video_entity.path, new_path)

        return video_entity.model_dump()

    @router.delete("/api/videos/{id}")
    def delete_video(self, id: int) -> APIMessage:
        video_entity = self.__get(id)
        os.remove(video_entity.path)
        self.session.delete(video_entity)
        self.session.commit()

        return APIMessage(detail="Deleted")


@cbv(router)
class ComicCBV:
    session: Session = Depends(db.get_session)

    def __del__(self):
        self.session.close()

    @router.get("/api/comics")
    def get_all(self, valid = True) -> List[ComicEntity]:
        comic_entities = self.session.exec(select(ComicEntity)).all()
        if valid:
            return [comic.model_dump() for comic in comic_entities]
        else:
            invalid_comics: List[ComicEntity] = []
            for comic in comic_entities:
                if not os.path.exists(comic.path):
                    invalid_comics.append(comic)
            return [comic.model_dump() for comic in invalid_comics]

    def __get(self, id: int) -> ComicEntity:
        statement = select(ComicEntity).where(ComicEntity.id == id)
        comic_entity = self.session.exec(statement).first()
        if comic_entity is None:
            abort(404, "Comic not found")
        return comic_entity

    @router.get("/api/comics/{id}")
    def get(self, id: int) -> ComicEntity:
        comic_entity = self.__get(id)
        return comic_entity.model_dump()

    @router.post("/api/comics/{id}/favor")
    def favor(self, id: int) -> APIMessage:
        comic_entity = self.__get(id)
        comic_entity.favorited = True
        self.session.add(comic_entity)
        self.session.commit()
        return APIMessage(detail="Favorited")

    @router.delete("/api/comics/{id}/favor")
    def unfavor(self, id: int) -> APIMessage:
        comic_entity = self.__get(id)
        comic_entity.favorited = False
        self.session.add(comic_entity)
        self.session.commit()
        return APIMessage(detail="Unfavorited")

    @router.post("/api/comics/{id}/refresh")
    def refresh_comic(self, id):
        comic = self.__get(id)
        comic_entity_init = ComicEntity.from_path(pathlib.Path(comic.path), comic.id)
        with comicfile.create(comic.path) as cf:
            comic.page = cf.page
            comic.updateTime = comic_entity_init.updateTime
            ComicLoader.gen_comic_cover(comic, cf)
            self.session.add(comic)
            self.session.commit()
            self.session.refresh(comic)

        return comic.model_dump()

    class RenameRequest(BaseModel):
        name: str

    @router.post("/api/comics/{id}/rename")
    def rename_comic(self, id: int, req: RenameRequest):
        comic = self.__get(id)
        if not os.path.exists(comic.path):
            abort(404, "Comic not found in filesystem")
        new_name = req.name
        if new_name is None:
            abort(400, "Name is required")
        if new_name == comic.name:
            abort(400, "Name is same")
        new_path = os.path.join(os.path.dirname(comic.path), new_name)
        if os.path.exists(new_path):
            abort(400, "File already exists")
        new_comic_statement = select(ComicEntity).where(
            or_(ComicEntity.name == new_name, ComicEntity.path == new_path)
        )
        new_comic = self.session.exec(new_comic_statement).first()
        if new_comic is not None:
            abort(400, "Comic with same name/path already exists")
        if comicfile.comic_cache.get(comic.path) is not None:
            cf = comicfile.comic_cache[comic.path]
            cf.close()
            del comicfile.comic_cache[comic.path]
        os.rename(comic.path, new_path)
        comic.name = new_name
        comic.path = new_path
        self.session.add(comic)
        self.session.commit()
        self.session.refresh(comic)
        return comic.model_dump()

    @router.delete("/api/comics/{id}")
    def delete_comic(self, id: int, permenant: bool = False):
        comic = self.__get(id)
        if comic.favorited:
            abort(400, "Cannot delete favorited comic")
        path = pathlib.Path(comic.path)
        if path.exists():
            cf = comicfile.create_open(comic.path)
            if cf is not None:
                cf.close()

        if permenant == False:
            comic.archived = True
            self.session.add(comic)
        else:
            self.session.delete(comic)
            cover = os.path.join(global_data.Config.nginx_comic_path, f"{id}_0.jpg")
            if os.path.exists(cover):
                os.remove(cover)
        try:
            if path.is_dir() and comic.page == len(list(path.glob("*"))):
                print("remove dir", comic.path)
                shutil.rmtree(comic.path)
            else:
                print("remove file", comic.path)
                os.remove(comic.path)
        except Exception as e:
            abort(500, f"Failed to delete comic file with ex: {e}")
        self.session.commit()

        return APIMessage(detail="Deleted")

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

    @router.get("/api/comics/{id}/{page}")
    def get(self, id: int, page: int) -> Response:
        comic = self.__get(id)
        cf = comicfile.create_open(comic.path)
        if cf is None:
            abort(404, "Comic file not found")
        ok, bytes = cf.read(page - 1)
        if ok:
            return Response(
                content=bytes,
                media_type="image/jpeg",
                headers={"cache-control": "max-age=604800"},
            )

        abort(404, "Page not found")

    @router.post("/api/comics/{id}/{page}/like")
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

    @router.post("/api/comics/{id}/{page}/cover")
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


@cbv(router)
class ImageCBV:
    @router.get("/api/images")
    def get_images(self):
        # get all images and updateTime then order by updateTime
        files = []
        for root, dirs, files in os.walk(global_data.Config.nginx_image_path):
            break
        images = []
        for f in files:
            path = os.path.join(root, f)
            stat = os.stat(path)
            images.append((f, path, datetime.datetime.fromtimestamp(stat.st_mtime)))
        images.sort(key=lambda x: x[1], reverse=True)
        return [
            FileEntity(id=i, name=f[0], path=f[1], size=0, updateTime=f[2]).model_dump()
            for i, f in enumerate(images)
        ]


app.include_router(router)


def process_view_history():
    t = threading.Timer(300, process_view_history)
    t.daemon = True
    t.start()
    if os.path.exists(global_data.Config.nginx_access_log_path):
        # log format: [02/Nov/2023:23:30:03 +0800] "GET /api/comics/358/1 HTTP/1.1"
        comic_dict = {}
        video_dict = {}
        with open(global_data.Config.nginx_access_log_path, "r") as f:
            lines = f.readlines()
            if len(lines) == 0:
                return
            regex = r"\[(.*) \+\d+\] \"GET /api/(\w+)/(\d+)/(\d+)"
            for line in lines:
                m = re.match(regex, line, re.I)
                if not m:
                    continue
                type = m.group(2)
                id = int(m.group(3))
                position = int(m.group(4))
                time_str = m.group(1)
                time = datetime.datetime.strptime(time_str, "%d/%b/%Y:%H:%M:%S")
                if type == "comics":
                    comic_dict[id] = time, position
                elif type == "videos":
                    video_dict[id] = time
        if len(comic_dict.keys()) > 0:
            print("update comic view history")
            with Session(db.engine) as session:
                for id, tuple in comic_dict.items():
                    time, position = tuple
                    e = session.exec(
                        select(ComicEntity).where(ComicEntity.id == id)
                    ).one_or_none()
                    if e is not None:
                        e.lastViewedPosition = position
                        e.lastViewedTime = time
                        session.add(e)
                        session.commit()
                    else:
                        print(f"comic {id} not found")
        if len(video_dict.keys()) > 0:
            with Session(db.engine) as session:
                for id, time in video_dict.items():
                    e = session.exec(
                        select(VideoEntity).where(VideoEntity.id == id)
                    ).one_or_none()
                    if e is not None:
                        e.lastViewedPosition = time
                        session.add(e)
                        session.commit()
                    else:
                        print(f"video {id} not found")
        with open(global_data.Config.nginx_access_log_path, "w") as f:
            pass


if __name__ == "__main__":
    # setup db
    SQLModel.metadata.create_all(db.engine)

    # load new comic and video
    # ComicLoader().work()
    # VideoLoader().work()

    # setup timer
    t = threading.Timer(1, process_view_history)
    t.daemon = True
    t.start()

    # run
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
