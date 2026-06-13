"""Video API endpoints"""
import os
from typing import List
from fastapi import APIRouter, Depends
from fastapi_utils.api_model import APIMessage
from fastapi_utils.cbv import cbv
from sqlmodel import Session, select

import db
import global_data
import util
from core.exceptions import abort
from model import VideoEntity


router = APIRouter()


@cbv(router)
class VideoCBV:
    session: Session = Depends(db.get_session)

    @router.get("/api/videos", tags=["videos"])
    def get_all(self, top: int = None) -> List[VideoEntity]:
        # Hide videos whose file is gone (flag maintained by the scan reconcile),
        # so an unmounted drive doesn't surface ghost entries.
        statement = select(VideoEntity).where(
            VideoEntity.missing == False  # noqa: E712
        ).order_by(VideoEntity.updateTime.desc())
        if top is not None:
            statement = statement.limit(top)
        video_entities = self.session.exec(statement).all()

        return [v.model_dump() for v in video_entities]

    def __get(self, id: int) -> VideoEntity:
        statement = select(VideoEntity).where(VideoEntity.id == id)
        video_entity = self.session.exec(statement).first()
        if video_entity is None:
            abort(404, "Video not found")
        return video_entity

    @router.get("/api/videos/{id}", tags=["videos"])
    def get(self, id: int) -> VideoEntity:
        video_entity = self.__get(id)
        new_name = str(id)
        new_path = os.path.join(global_data.Config.nginx_video_path, new_name)
        util.create_soft_link(video_entity.path, new_path)

        return video_entity.model_dump()

    @router.delete("/api/videos/{id}", tags=["videos"])
    def delete(self, id: int, permanent: bool = False) -> APIMessage:
        video_entity = self.__get(id)
        if not permanent:
            video_entity.archived = True
            self.session.add(video_entity)
        else:
            self.session.delete(video_entity)
        try:
            os.remove(video_entity.path)
        except FileNotFoundError:
            pass
        self.session.commit()

        return APIMessage(detail="Deleted")
