from datetime import datetime
import pathlib
from pydantic import BaseModel
from sqlmodel import Field, SQLModel

def get_dir_size(path: pathlib.Path) -> int:
    size = 0
    for p in path.iterdir():
        if p.is_dir():
            size += get_dir_size(p)
        else:
            size += p.stat().st_size
    return size

class FileEntity(SQLModel):
    id: int = Field(primary_key=True)
    size: int
    name: str
    path: str
    updateTime: datetime
    archived: bool = Field(default=False)
    favorited: bool = Field(default=False)
    lastViewedTime: datetime | None = Field(default=None)
    lastViewedPosition: int = Field(default=0)
    coverPosition: int = Field(default=0)
    entityUpdateTime: datetime = Field(default=datetime.now())

    @staticmethod
    def from_path(path: pathlib.Path):
        stat = path.stat()
        return FileEntity(
            id=0,
            size=stat.st_size if path.is_file() else get_dir_size(path),
            name=path.name,
            path=str(path),
            updateTime=datetime.fromtimestamp(stat.st_mtime),
        )


class ComicEntity(FileEntity, table=True):
    page: int = Field(default=0)

    @staticmethod
    def from_path(path: pathlib.Path, id: int):
        ret = ComicEntity(**FileEntity.from_path(path).model_dump())
        ret.id = id
        return ret


class VideoEntity(FileEntity, table=True):
    durationInSecond: int = Field(default=0)

    @staticmethod
    def from_path(path: pathlib.Path, id: int):
        ret = VideoEntity(**FileEntity.from_path(path).model_dump())
        ret.id = id
        return ret


class ImageEntity(FileEntity):
    @staticmethod
    def from_path(path: pathlib.Path, id: int):
        ret = VideoEntity(**FileEntity.from_path(path).model_dump())
        ret.id = id
        return ret
