"""Home page feed: what to pick up next, across media types.

One request returns every section, each holding up to ``HOME_SIZE`` items per
type; the frontend merges the types and trims each row. Archived and missing
items never show up. Image albums have no favorites, and only comics and image
albums track reading progress (image progress is in memory, so it's gone after
a restart).
"""
import random
from typing import List

from fastapi import APIRouter, Depends
from fastapi_utils.cbv import cbv
from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import Session, col, select

import db
from api import images
from model import ComicEntity, ImageEntity, VideoEntity

router = APIRouter()

HOME_SIZE = 12


class HomeSection(BaseModel):
    comics: List[ComicEntity] = []
    videos: List[VideoEntity] = []
    images: List[ImageEntity] = []


class HomeResponse(BaseModel):
    # Started but not finished, most recently read first.
    continueReading: HomeSection
    # Newest files first.
    recent: HomeSection
    favorites: HomeSection
    random: HomeSection


def _in_progress(e) -> bool:
    return e.lastViewedTime is not None and 0 < e.lastViewedPosition < e.page


@cbv(router)
class HomeCBV:
    session: Session = Depends(db.get_session)

    def _select(self, entity):
        return select(entity).where(
            entity.archived == False,  # noqa: E712
            entity.missing == False,  # noqa: E712
        )

    def _all(self, statement) -> list:
        return list(self.session.exec(statement.limit(HOME_SIZE)).all())

    @router.get("/api/home", tags=["home"])
    def get(self) -> HomeResponse:
        album_list = [e for e in images.all_entities() if not e.archived and not e.missing]

        continue_comics = self._all(
            self._select(ComicEntity)
            .where(
                col(ComicEntity.lastViewedTime).is_not(None),
                ComicEntity.lastViewedPosition > 0,
                ComicEntity.lastViewedPosition < ComicEntity.page,
            )
            .order_by(col(ComicEntity.lastViewedTime).desc())
        )
        continue_images = sorted(
            filter(_in_progress, album_list), key=lambda e: e.lastViewedTime, reverse=True
        )[:HOME_SIZE]

        def newest(entity):
            return self._all(self._select(entity).order_by(col(entity.updateTime).desc()))

        def favorites(entity):
            return self._all(
                self._select(entity)
                .where(entity.favorited == True)  # noqa: E712
                .order_by(col(entity.updateTime).desc())
            )

        def shuffled(entity):
            return self._all(self._select(entity).order_by(func.random()))

        return HomeResponse(
            continueReading=HomeSection(comics=continue_comics, images=continue_images),
            recent=HomeSection(
                comics=newest(ComicEntity),
                videos=newest(VideoEntity),
                images=sorted(album_list, key=lambda e: e.updateTime, reverse=True)[:HOME_SIZE],
            ),
            favorites=HomeSection(comics=favorites(ComicEntity), videos=favorites(VideoEntity)),
            random=HomeSection(
                comics=shuffled(ComicEntity),
                videos=shuffled(VideoEntity),
                images=random.sample(album_list, min(HOME_SIZE, len(album_list))),
            ),
        )
