"""Image API endpoints"""
import datetime
import os
from typing import List
from fastapi import APIRouter
from fastapi_utils.cbv import cbv

import global_data
from model import ImageEntity


router = APIRouter()


@cbv(router)
class ImageCBV:
    @router.get("/api/images", tags=["images"])
    def get_all(self, top: int = None) -> List[ImageEntity]:
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
            ImageEntity(id=i, name=f[0], path=f[1], size=0, updateTime=f[2]).model_dump()
            for i, f in enumerate(images) if top is None or i < int(top)
        ]
