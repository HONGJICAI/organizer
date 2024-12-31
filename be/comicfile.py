from abc import abstractmethod
import os
from typing import List
import zipfile
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


def create(filepath: str) -> Comicfile or None:
    _, ext = os.path.splitext(filepath)
    if ext == ".zip":
        return ZipComicfile(filepath)
    elif ext == ".rar":
        return RarComicfile(filepath)
    elif ext == "":
        return DirectoryComicfile(filepath)

    return None


class ZipRarComicfile(Comicfile):
    _archive: zipfile.ZipFile | rarfile.RarFile
    _namelist: List[str] = None
    _page: int = None

    def __init__(self, filepath: str):
        self.filepath = filepath

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
        if self._archive:
            self._archive.close()

    @property
    def page(self):
        return self._page

    def open(self):
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
    _page: int = None
    _namelist: List[str] = None

    def __init__(self, filepath: str):
        self.filepath = filepath
        self._namelist = self._valid_entries = list(
            filter(
                lambda x: x.is_file() and os.path.splitext(x.name)[-1] in allowImgs,
                list(os.scandir(filepath)),
            )
        )
        self._page = len(self._namelist)

    def __enter__(self):
        return self

    def __exit__(self, type, value, trace):
        pass

    @property
    def page(self):
        return self._page

    def read(self, page):
        if page >= self._page:
            return False, None
        with open(os.path.join(self.filepath, self._namelist[page]), "rb") as f:
            return True, f.read()
