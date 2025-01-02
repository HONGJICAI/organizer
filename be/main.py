from abc import abstractmethod
import re
import subprocess
import threading
import global_data
import datetime
import io
import pathlib
import db
from typing import List
from flask import Flask, Response, abort, jsonify, request
import os
from flask_cors import CORS
from PIL import Image
from sqlmodel import SQLModel, Session, create_engine, select
from flasgger import Swagger
from rich.traceback import install
from rich.progress import track
from loader import ComicLoader, VideoLoader

import util
from model import (
    ComicEntity,
    ComicResponse,
    FileEntity,
    LikeEntity,
    VideoEntity,
    ViewHistoryEntity,
)
import comicfile

install(show_locals=True)

app = Flask(__name__)
cors = CORS(app)
swagger = Swagger(app)

app.config["CORS_HEADERS"] = "Content-Type"


@app.route("/api/similar", methods=["GET"])
def get_similar_files():
    path = request.args.get("path")
    groups = find_similar_file.find_similar_files([path])
    ret = []
    for g in groups:
        ret.append([f.__dict__ for f in g])
    return ret


@app.route("/api/videos", methods=["GET"])
def get_videos():
    with Session(db.engine) as session:
        statement = select(VideoEntity)
        video_entities = session.exec(statement).all()

        return [v.dict() for v in video_entities]


@app.route("/api/videos/<int:id>", methods=["GET"])
def get_video(id: int):
    with Session(db.engine) as session:
        statement = select(VideoEntity).where(VideoEntity.id == id)
        video_entity = session.exec(statement).first()
        if video_entity is None:
            abort(404)

        new_name = str(id)
        new_path = os.path.join(global_data.Config.nginx_video_path, new_name)
        util.create_soft_link(video_entity.path, new_path)

    return video_entity.dict()


@app.route("/api/videos/<int:id>", methods=["Delete"])
def delete_video(id: int):
    with Session(db.engine) as session:
        statement = select(VideoEntity).where(VideoEntity.id == id)
        video_entity = session.exec(statement).first()
        if video_entity is None:
            abort(404)

        os.remove(video_entity.path)

        session.delete(video_entity)
        session.commit()

    return Response(status=200)


def clean_comic_entity():
    with Session(db.engine) as session:
        statement = select(ComicEntity)
        comic_entities = session.exec(statement).all()
        entities_todelete = []
        for c in comic_entities:
            if not os.path.exists(c.path):
                statement = (
                    select(LikeEntity)
                    .where(LikeEntity.type == "comic")
                    .where(LikeEntity.id == c.id)
                )
                like = session.exec(statement).first()
                if like is not None:
                    print("could not delete comic if liked")
                else:
                    entities_todelete.append(c)
        for c in entities_todelete:
            session.delete(c)


@app.route("/api/comics", methods=["GET"])
def get_comics():
    """
    get all comics info.
    ---
    responses:
      200:
        description: all comics info
    """
    with Session(db.engine) as session:
        result = session.exec(select(ComicEntity)).all()
        like_entities = session.exec(
            select(LikeEntity).where(LikeEntity.type == "comic")
        ).all()
        like_ids = set([e.id for e in like_entities])
        view_history_entities = session.exec(
            select(ViewHistoryEntity).where(ViewHistoryEntity.type == "comic")
        ).all()
        # group by id
        id2history = {}
        for e in view_history_entities:
            id2history[e.id] = e
        none = ViewHistoryEntity()
        none.position = 0
        none.updateTime = None

        comic_entities = [
            ComicResponse(
                **comic.dict(),
                like=True if comic.id in like_ids else False,
                lastViewed=id2history.get(comic.id, none).position,
                lastViewedTime=id2history.get(comic.id, none).updateTime,
            )
            for comic in result
        ]

        return [comic.dict() for comic in comic_entities]


@app.route("/api/comics/<int:id>", methods=["GET"])
def get_comic(id):
    """
    get specific comic info.
    ---
    parameters:
      - name: id
        type: integer
        in: path
        required: true
        description: comic id
    responses:
      200:
        description: Specific comic info
      404:
        description: Specific comic id not exist
    """
    with Session(db.engine) as session:
        statement = select(ComicEntity).where(ComicEntity.id == id)
        comic = session.exec(statement).first()
        if comic is None:
            abort(404)

        return ComicResponse(**comic.dict(), like=False, lastViewedTime=None).dict()


@app.route("/api/comics/<int:id>/like", methods=["POST"])
def like_comic(id):
    with Session(db.engine) as session:
        statement = select(ComicEntity).where(ComicEntity.id == id)
        comic = session.exec(statement).first()
        if comic is None:
            abort(404)
        like_entity = LikeEntity(type="comic", id=id)
        session.add(like_entity)
        session.commit()

    return Response(status=200)


@app.route("/api/comics/<int:id>/unlike", methods=["POST"])
def unlike_comic(id):
    with Session(db.engine) as session:
        statement = select(ComicEntity).where(ComicEntity.id == id)
        comic = session.exec(statement).first()
        if comic is None:
            abort(404)
        statement = (
            select(LikeEntity)
            .where(LikeEntity.type == "comic")
            .where(LikeEntity.id == id)
        )
        like_entity = session.exec(statement).first()
        if like_entity:
            session.delete(like_entity)
            session.commit()

    return Response(status=200)


@app.route("/api/comics/<int:id>/refresh", methods=["POST"])
def refresh_comic(id):
    with Session(db.engine) as session:
        statement = select(ComicEntity).where(ComicEntity.id == id)
        comic = session.exec(statement).first()
        if comic is None:
            abort(404)

        with comicfile.create(comic.path) as cf:
            comic.page = cf.page
            ComicLoader.gen_comic_cover(comic, cf)
            session.add(comic)
            session.commit()
            session.refresh(comic)

            like = (
                True
                if session.exec(
                    select(LikeEntity)
                    .where(LikeEntity.type == "comic")
                    .where(LikeEntity.id == id)
                ).one_or_none()
                else False
            )
            view_entity = session.exec(
                select(ViewHistoryEntity)
                .where(ViewHistoryEntity.type == "comic")
                .where(ViewHistoryEntity.id == id)
            ).one_or_none()
            last_viewed_time = (
                view_entity.updateTime if view_entity is not None else None
            )
            return ComicResponse(
                **comic.dict(), like=like, lastViewedTime=last_viewed_time
            ).dict()


@app.route("/api/comics/<int:id>", methods=["DELETE"])
def delete_comic(id):
    permenant = request.args.get("permenant", "false")
    with Session(db.engine) as session:
        statement = select(ComicEntity).where(ComicEntity.id == id)
        comic = session.exec(statement).first()
        if comic is None:
            abort(404)

        cf: comicfile.Comicfile = global_data.comic.comic_caches.get(id, None)
        if cf is not None:
            cf.close()
            del global_data.comic.comic_caches[comic.id]

        if permenant == "false":
            comic.archive = True
            session.add(comic)
        else:
            session.delete(comic)
            cover = os.path.join(global_data.Config.nginx_comic_path, f"{id}_0.jpg")
            if os.path.exists(cover):
                os.remove(cover)
        try:
            if os.path.exists(comic.path):
                os.remove(comic.path)
        except Exception as e:
            return jsonify({"error": str(e)}), 500
        session.commit()

    return Response(status=200)


@app.route("/api/comics/<int:id>/<int:page>", methods=["GET"])
def get_comicpage(id, page):
    """returning image from zip file
    returning mimetype is "image/jpeg"
    ---
    parameters:
      - name: id
        type: int
        required: true
        default: 0
        description: comic id
      - name: page
        type: int
        in: path
        required: true
        default: 0
        description: comic page
    responses:
      200:
        description: Specific comic image with mimetype="image/jpeg"
      404:
        description: Specific comic id or comic page not exist
    """

    with Session(db.engine) as session:
        statement = select(ComicEntity).where(ComicEntity.id == id)
        comic = session.exec(statement).first()

    if comic is None:
        abort(404)

    cf = global_data.comic.comic_caches.get(comic.id, None)
    if cf is None:
        cf = comicfile.create(comic.path)
        cf.open()
        global_data.comic.comic_caches[comic.id] = cf
    ok, bytes = cf.read(page - 1)
    if ok:
        rsp = Response(
            response=bytes,
            mimetype="image/jpeg",
            headers={"cache-control": "max-age=604800"},
        )
        return rsp

    abort(404)


@app.route("/api/comics/<int:id>/<int:page>/like", methods=["POST"])
def like_comicpage(id, page):
    """like comic page
    ---
    parameters:
      - name: id
        type: int
        required: true
        default: 0
        description: comic id
      - name: page
        type: int
        in: path
        required: true
        default: 0
        description: comic page
    responses:
      200:
        description: if ok
      404:
        description: Specific comic id or comic page not exist
    """

    with Session(db.engine) as session:
        statement = select(ComicEntity).where(ComicEntity.id == id)
        comic = session.exec(statement).first()

    if comic is None:
        abort(404)
    name = f"{comic.name}_{page}.jpg"
    path = os.path.join(global_data.Config.nginx_image_path, name)
    if not os.path.exists(path):
        cf = global_data.comic.comic_caches.get(comic.id, None)
        if cf is None:
            cf = comicfile.create(comic.path)
            cf.open()
            global_data.comic.comic_caches[comic.id] = cf
        ok, bytes = cf.read(page - 1)
        if ok:
            img = Image.open(io.BytesIO(bytes))
            img = img.convert("RGB")
            img.save(path, "JPEG")
            rsp = Response(status=200)
            return rsp

    abort(404)


@app.route("/api/comics/<int:id>/<int:page>/cover", methods=["POST"])
def set_comicpage_cover(id, page):
    """set comic page as cover
    ---
    parameters:
      - name: id
        type: int
        required: true
        default: 0
        description: comic id
      - name: page
        type: int
        in: path
        required: true
        default: 0
        description: comic page
    responses:
      200:
        description: if ok
      404:
        description: Specific comic id or comic page not exist
    """

    with Session(db.engine) as session:
        statement = select(ComicEntity).where(ComicEntity.id == id)
        comic = session.exec(statement).first()

    if comic is None:
        abort(404)
    cf = global_data.comic.comic_caches.get(comic.id, None)
    if cf is None:
        cf = comicfile.create(comic.path)
        cf.open()
        global_data.comic.comic_caches[comic.id] = cf
    if ComicLoader.gen_comic_cover(comic, cf, True, page):
        rsp = Response(status=200)
        return rsp

    abort(500)


@app.route("/api/images", methods=["GET"])
def get_images():
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
        FileEntity(id=i, name=f[0], path=f[1], size=0, updateTime=f[2]).dict()
        for i, f in enumerate(images)
    ]


def process_view_history():
    t = threading.Timer(300, process_view_history)
    t.daemon = True
    t.start()
    print("process view history...")
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
            with Session(db.engine) as session:
                for id, tuple in comic_dict.items():
                    time, position = tuple
                    e = session.exec(
                        select(ViewHistoryEntity)
                        .where(ViewHistoryEntity.type == "comic")
                        .where(ViewHistoryEntity.id == id)
                    ).one_or_none()
                    if e is not None:
                        e.position = position
                        e.updateTime = time
                    else:
                        e = ViewHistoryEntity(type="comic", id=id, updateTime=time, position=position)
                    session.add(e)
                session.commit()
        if len(video_dict.keys()) > 0:
            with Session(db.engine) as session:
                for id, time in video_dict.items():
                    e = session.exec(
                        select(ViewHistoryEntity)
                        .where(ViewHistoryEntity.type == "video")
                        .where(ViewHistoryEntity.id == id)
                    ).one_or_none()
                    if e is not None:
                        e.updateTime = time
                    else:
                        e = ViewHistoryEntity(type="video", id=id, updateTime=time)
                    session.add(e)
                session.commit()
        with open(global_data.Config.nginx_access_log_path, "w") as f:
            pass


@app.route("/api/status", methods=["GET"])
def get_status():
    ret = {
        "cache": len(global_data.comic.comic_caches),
        "caches": [{"id": id} for id in global_data.comic.comic_caches.keys()],
        "err_message": global_data.err_message,
    }
    return ret


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
    app.run(host="0.0.0.0", debug=True, port=8001)
