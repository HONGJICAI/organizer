from abc import abstractmethod
import io
import os
import pathlib
import threading
from typing import List
import zipfile
from cachetools import TTLCache, cached
from PIL import Image
import rarfile

allowImgs = [".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"]
allowZips = [".zip", ".rar"]


def is_page(name: str) -> bool:
    """Whether an archive or folder entry is a comic page.

    macOS adds AppleDouble metadata to archives it creates: ``._001.jpg``
    files, usually under ``__MACOSX/``. They carry image extensions but aren't
    images, and they can sort ahead of the real first page, so they're skipped
    along with other hidden files.
    """
    parts = name.replace("\\", "/").split("/")
    if parts[-1].startswith(".") or "__MACOSX" in parts:
        return False
    return os.path.splitext(name)[1].lower() in allowImgs


def image_info(fp) -> dict:
    """Width, height and format of the image in ``fp``.

    Pillow reads only the header here, so a stream needs just its first few KB.
    Raises if it isn't an image Pillow can identify.
    """
    with Image.open(fp) as img:
        return {"width": img.width, "height": img.height, "format": img.format}


def order_pages(names) -> List[str]:
    """Page entries in reading order.

    Sorted by name; when every file name (ignoring its folder) is a number,
    sorted numerically within each folder instead, so ``Title/2.jpg`` comes
    before ``Title/10.jpg``.
    """
    pages = [n for n in names if is_page(n)]
    split = [os.path.split(n.replace("\\", "/")) for n in pages]
    if pages and all(os.path.splitext(base)[0].isdigit() for _, base in split):
        order = sorted(range(len(pages)), key=lambda i: (split[i][0], int(os.path.splitext(split[i][1])[0])))
        return [pages[i] for i in order]
    return sorted(pages)

mediaTypes = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
}


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

    @property
    def namelist(self) -> List[str]:
        """
        return the list of comic file
        """
        if not self._opened:
            raise Exception("comic file not opened")
        return self._namelist

    @abstractmethod
    def page_sizes(self) -> List[int]:
        """Uncompressed size in bytes of each page, in page order."""

    def page_info(self, page: int) -> dict | None:
        """image_info() of a 0-based page, or None when there is no such page.

        Reads the whole page; subclasses that can stream override this.
        """
        ok, buf = self.read(page)
        return image_info(io.BytesIO(buf)) if ok else None


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

    def page_sizes(self) -> List[int]:
        # From the archive's directory: no page is decompressed.
        return [self._archive.getinfo(name).file_size for name in self.namelist]

    def page_info(self, page: int) -> dict | None:
        if not 0 <= page < self.page:
            return None
        if isinstance(self._archive, zipfile.ZipFile):
            # Decompresses only as far as Pillow reads (the image header).
            with self._archive.open(self._namelist[page]) as f:
                return image_info(f)
        # rarfile extracts through an external tool; reading the page whole is
        # cheaper than letting Pillow seek around in that stream.
        return super().page_info(page)

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
            self._namelist = order_pages(self._archive.namelist())
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
        self._namelist = order_pages(e.name for e in os.scandir(self._filepath) if e.is_file())
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

    def page_sizes(self) -> List[int]:
        return [os.path.getsize(os.path.join(self._filepath, name)) for name in self.namelist]

    def page_info(self, page: int) -> dict | None:
        if not 0 <= page < self.page:
            return None
        with open(os.path.join(self._filepath, self._namelist[page]), "rb") as f:
            return image_info(f)

    def read(self, page):
        if page >= self._page:
            return False, None
        with open(os.path.join(self._filepath, self._namelist[page]), "rb") as f:
            return True, f.read()
