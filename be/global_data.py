import json
import queue
import os
from typing import List, Dict

from cachetools import TTLCache
import model


class ComicGlobalData:
    def __init__(self) -> None:
        self._comic_caches = TTLCache(maxsize=3, ttl=300)

    @property
    def comic_caches(self):
        return self._comic_caches


comic = ComicGlobalData()
err_message = []


class Config:
    nginx_path = os.path.join(__file__, "..", "nginx")
    nginx_access_log_path = os.path.join(nginx_path, "logs", "file.access.log")
    nginx_html_path = os.path.join(nginx_path, "html")
    nginx_video_path = os.path.join(nginx_html_path, "videos")
    nginx_comic_path = os.path.join(nginx_html_path, "comics")
    nginx_image_path = os.path.join(nginx_html_path, "images")

    class Comic:
        scan_pathes = [
        ]

    class Video:
        scan_pathes = [
        ]
