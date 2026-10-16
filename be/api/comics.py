"""Comic API endpoints"""
import os
import pathlib
import shutil
from datetime import datetime
from typing import List
from fastapi import APIRouter, Depends, Query
from fastapi_utils.api_model import APIMessage
from fastapi_utils.cbv import cbv
from sqlmodel import Session, select, or_

import comicfile
import db
import duplicates
import stats
import events
import global_data
import util
from core.exceptions import abort
from loader import ComicLoader
from model import ComicEntity
from schemas.comic import (
    ComicDetailResponse,
    DuplicateGroup,
    DuplicatesResponse,
    ComicPageDetailResponse,
    ComicRenameRequest,
    ComicRenameResponse,
    ComicStatsResponse,
)
from schemas.common import CheckRequest, CheckResponse, CheckResult, FavorResponse
from util import PathState


router = APIRouter()


@cbv(router)
class ComicCBV:
    session: Session = Depends(db.get_session)

    @router.get("/api/comics", tags=["comics"], response_model_exclude_none=True, response_model_exclude_defaults=True)
    def get_all(self, fileMiss: bool = False, top: int = None) -> List[ComicEntity]:
        # `missing` is maintained by the scan reconcile (loader.work), so this
        # filters on the stored flag instead of stat-ing the filesystem on every
        # request. fileMiss=true is the organize page asking for the gone files;
        # the default list hides them so an unmounted drive doesn't show ghosts.
        statement = select(ComicEntity).where(
            ComicEntity.missing == fileMiss  # noqa: E712
        ).order_by(ComicEntity.updateTime.desc())
        if top is not None:
            statement = statement.limit(top)
        comic_entities = self.session.exec(statement).all()
        return [comic.model_dump() for comic in comic_entities]

    @router.post(
        "/api/comics/check",
        tags=["comics"],
        responses={
            200: {"model": CheckResponse},
            400: {"model": dict},
        },
    )
    def check(self, req: CheckRequest) -> CheckResponse:
        # Re-verify on disk whether specific comics still exist, without the
        # cost of a full library scan. This is what the organize page uses to
        # let an SMB share settle: files that came back drop off the list, while
        # a momentary mount blip (UNKNOWN) is reported but never acted on, so we
        # don't flip a healthy file to "missing" on jitter.
        if not req.ids:
            abort(400, "ids is required")
        ids = list(dict.fromkeys(req.ids))
        entities = {
            e.id: e
            for e in self.session.exec(
                select(ComicEntity).where(ComicEntity.id.in_(ids))
            ).all()
        }
        # Probe the filesystem off the DB session (pure stat, parallelizable);
        # SMB latency is the cost we want to fan out, not serialize.
        found = [(i, entities[i].path) for i in ids if i in entities]
        states = util.probe_paths([path for _, path in found])
        changed = False
        results = []
        for (i, _), state in zip(found, states):
            entity = entities[i]
            if state == PathState.PRESENT and entity.missing:
                entity.missing = False
                self.session.add(entity)
                changed = True
            elif state == PathState.ABSENT and not entity.missing:
                entity.missing = True
                self.session.add(entity)
                changed = True
            results.append(CheckResult(id=i, status=state.value))
        for i in ids:
            if i not in entities:
                results.append(CheckResult(id=i, status="notfound"))
        if changed:
            self.session.commit()
        return CheckResponse(results=results)

    @router.get(
        "/api/comics/stats",
        tags=["comics"],
        responses={400: {"model": dict}},
    )
    def get_stats(
        self, months: int = Query(default=12, ge=1, le=60)
    ) -> ComicStatsResponse:
        # Declared before /{id} so the literal path isn't parsed as an id.
        return stats.comic_stats(self.session, months)

    @router.get(
        "/api/comics/duplicates",
        tags=["comics"],
        responses={
            200: {"model": DuplicatesResponse},
            400: {"model": dict},
        },
    )
    def find_duplicates(
        self, threshold: float = Query(default=0.85, ge=0.5, le=1.0)
    ) -> DuplicatesResponse:
        # Archived rows are tombstones and missing ones have no file to keep or
        # delete, so only live comics take part. Declared before /{id} so the
        # literal path isn't parsed as an id.
        comics = self.session.exec(
            select(ComicEntity)
            .where(ComicEntity.archived == False)  # noqa: E712
            .where(ComicEntity.missing == False)  # noqa: E712
            .order_by(ComicEntity.name)
        ).all()
        groups = []
        for indices, exact in duplicates.find_groups([c.name for c in comics], threshold):
            items = [comics[i] for i in indices]
            groups.append(
                DuplicateGroup(
                    exact=exact,
                    keepId=duplicates.pick_keep(items),
                    items=[c.model_dump() for c in items],
                )
            )
        return DuplicatesResponse(groups=groups)

    def __get(self, id: int) -> ComicEntity:
        statement = select(ComicEntity).where(ComicEntity.id == id)
        comic_entity = self.session.exec(statement).first()
        if comic_entity is None:
            abort(404, "Comic not found")
        return comic_entity

    @router.get("/api/comics/{id}", tags=["comics"])
    def get(self, id: int) -> ComicEntity:
        comic_entity = self.__get(id)
        return comic_entity.model_dump()

    @router.get(
        "/api/comics/{id}/detail",
        tags=["comics"],
        responses={
            200: {"model": ComicDetailResponse},
            404: {"model": dict},
        },
    )
    def detail(self, id: int):
        comic = self.__get(id)
        cf = comicfile.create_open(comic.path)
        if cf is None:
            abort(404, "Comic file not found")
        pageDetails = [
            ComicPageDetailResponse(name=name, size=size)
            for name, size in zip(cf.namelist, cf.page_sizes())
        ]
        return ComicDetailResponse(pageDetails=pageDetails)

    @router.post(
        "/api/comics/{id}/favor",
        tags=["comics"],
        responses={
            200: {"model": FavorResponse},
            404: {"model": dict},
        },
    )
    def favor(self, id: int) -> FavorResponse:
        comic_entity = self.__get(id)
        comic_entity.favorited = True
        self.session.add(comic_entity)
        self.session.commit()
        return FavorResponse(favorited=True)

    @router.delete(
        "/api/comics/{id}/favor",
        tags=["comics"],
        responses={
            200: {"model": FavorResponse},
            404: {"model": dict},
        },
    )
    def unfavor(self, id: int) -> FavorResponse:
        comic_entity = self.__get(id)
        comic_entity.favorited = False
        self.session.add(comic_entity)
        self.session.commit()
        return FavorResponse(favorited=False)

    @router.post(
        "/api/comics/{id}/refresh",
        tags=["comics"],
        responses={
            200: {"model": ComicEntity},
            404: {"model": dict},
        },
    )
    def refresh(self, id) -> ComicEntity:
        comic = self.__get(id)
        comic_entity_init = ComicEntity.from_path(pathlib.Path(comic.path), comic.id)
        with comicfile.create(comic.path) as cf:
            comic.page = cf.page
            comic.updateTime = comic_entity_init.updateTime
            ComicLoader.gen_comic_cover(comic, cf)
            # The cover JPEG is rewritten under the same filename, so bump the
            # version field that the frontend appends to the cover URL — this is
            # what busts the browser/nginx/CDN cache for the regenerated image.
            comic.entityUpdateTime = datetime.now()
            self.session.add(comic)
            self.session.commit()
            self.session.refresh(comic)

        return comic.model_dump()

    @router.post(
        "/api/comics/{id}/rename",
        tags=["comics"],
        responses={
            200: {"model": ComicRenameResponse},
            404: {"model": dict},
        },
    )
    def rename(self, id: int, req: ComicRenameRequest) -> ComicRenameResponse:
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
        from cachetools.keys import hashkey
        cache_key = hashkey(comic.path)
        if cache_key in comicfile.comic_cache:
            comicfile.comic_cache[cache_key].close()
            del comicfile.comic_cache[cache_key]
        os.rename(comic.path, new_path)
        comic.name = new_name
        comic.path = new_path
        self.session.add(comic)
        self.session.commit()
        return ComicRenameResponse(name=new_name)

    @router.delete("/api/comics/{id}", tags=["comics"])
    def delete(self, id: int, permanent: bool = False):
        comic = self.__get(id)
        if comic.favorited:
            abort(400, "Cannot delete favorited comic")
        path = pathlib.Path(comic.path)
        if path.exists():
            cf = comicfile.create_open(comic.path)
            if cf is not None:
                cf.close()

        events.record_delete(self.session, events.COMIC, comic, permanent)
        if not permanent:
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
        except FileNotFoundError:
            pass
        except Exception as e:
            abort(500, f"Failed to delete comic file with ex: {e}")
        self.session.commit()

        return APIMessage(detail="Deleted")
