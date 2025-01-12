from abc import abstractmethod
from functools import cache
import os
import pathlib
import threading
from typing import List
import zipfile
from cachetools import TTLCache, cached
import rarfile

allowImgs = [".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"]
allowZips = [".zip", ".rar"]


class Comicfile:
    @abstractmethod
    def read(self, page):
        """
        read specific page of comic
        """

    # @property
    # @abstractmethod
    # def path(self) -> str:
    #     """
    #     the file path of comic file
    #     """

    @property
    @abstractmethod
    def page(self) -> str:
        """
        the total page of comic file
        """

    def open(self):
        """
        open comic file
        """

    def close(self):
        """
        close comic file
        """

    # @property
    # def page(self) -> int:
    #     """
    #     the total page of comic file
    #     """
    #     return self.page


def create(filepath: str) -> Comicfile | None:
    path = pathlib.Path(filepath)
    if not path.exists():
        return None
    if path.is_dir():
        return DirectoryComicfile(filepath)
    else:
        ext = path.suffix.lower()
        if ext == ".zip":
            return ZipComicfile(filepath)
        elif ext == ".rar":
            return RarComicfile(filepath)


comic_lock = threading.Lock()
comic_cache = TTLCache(maxsize=3, ttl=120)


@cached(cache=comic_cache, lock=comic_lock)
def create_open(filepath: str) -> Comicfile | None:
    comic = create(filepath)
    if comic:
        comic.open()
        return comic
    return None


class ZipRarComicfile(Comicfile):
    def __init__(self, filepath: str):
        self.filepath = filepath
        self._archive: zipfile.ZipFile | rarfile.RarFile
        self._namelist: List[str] = None
        self._page: int = None
        self._opened = False

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, type, value, trace):
        self.close()

    def read(self, page):
        if page >= self.page:
            return False, None
        return True, self._archive.read(self._namelist[page])

    def close(self):
        self._opened = False
        if self._archive:
            self._archive.close()

    @property
    def page(self):
        return self._page

    def open(self):
        if self._opened:
            return
        self._opened = True
        if not self._namelist or not self._page:
            self._namelist = list(
                sorted(
                    filter(
                        lambda x: os.path.splitext(x)[-1].lower() in allowImgs,
                        self._archive.namelist(),
                    )
                )
            )
            # if all filename is number, sort by number
            if all(
                map(
                    lambda x: x.isdigit(),
                    map(lambda x: os.path.splitext(x)[0], self._namelist),
                )
            ):
                self._namelist = list(
                    sorted(self._namelist, key=lambda x: int(os.path.splitext(x)[0]))
                )
            self._page = len(self._namelist)


class ZipComicfile(ZipRarComicfile):
    def open(self):
        self._archive = zipfile.ZipFile(self.filepath)
        super().open()


class RarComicfile(ZipRarComicfile):
    def open(self):
        self._archive = rarfile.RarFile(self.filepath)
        super().open()


class DirectoryComicfile(Comicfile):
    def __init__(self, filepath: str):
        self._filepath = filepath
        self._page: int = None
        self._namelist: List[str] = None
        self._filepath: str
        self._opened = False

    def open(self):
        if self._opened:
            return
        self._opened = True
        self._namelist = self._valid_entries = list(
            filter(
                lambda x: x.is_file() and os.path.splitext(x.name)[-1] in allowImgs,
                list(os.scandir(self._filepath)),
            )
        )
        self._page = len(self._namelist)

    def close(self):
        self._opened = False

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, type, value, trace):
        self.close()

    @property
    def page(self):
        return self._page

    def read(self, page):
        if page >= self._page:
            return False, None
        with open(os.path.join(self._filepath, self._namelist[page]), "rb") as f:
            return True, f.read()
