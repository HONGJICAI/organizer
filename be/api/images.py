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
        image_dir = global_data.Config.nginx_image_path
        if not os.path.isdir(image_dir):
            return []
        filenames = [f for f in os.listdir(image_dir) if os.path.isfile(os.path.join(image_dir, f))]
        images = []
        for f in filenames:
            path = os.path.join(image_dir, f)
            stat = os.stat(path)
            images.append((f, path, datetime.datetime.fromtimestamp(stat.st_mtime)))
        images.sort(key=lambda x: x[1], reverse=True)
        return [
            ImageEntity(id=i, name=f[0], path=f[1], size=0, updateTime=f[2]).model_dump()
            for i, f in enumerate(images) if top is None or i < int(top)
        ]
