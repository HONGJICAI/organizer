from datetime import datetime
import pathlib
from pydantic import BaseModel
from sqlmodel import Field, SQLModel

import comicfile


class FileEntity(SQLModel):
    id: int = Field(primary_key=True)
    size: int
    name: str
    path: str
    updateTime: datetime
    archive: bool = Field(default=False)

    @staticmethod
    def from_path(path: pathlib.Path):
        stat = path.stat()
        return FileEntity(
            id=0,
            size=stat.st_size,
            name=path.name,
            path=str(path),
            updateTime=datetime.fromtimestamp(stat.st_mtime),
        )


class ComicEntity(FileEntity, table=True):
    page: int = Field(default=0)

    @staticmethod
    def from_path(path: pathlib.Path, id: int):
        ret = ComicEntity(**FileEntity.from_path(path).dict())
        ret.id = id
        return ret


class VideoEntity(FileEntity, table=True):
    durationInSecond: int = Field(default=0)

    @staticmethod
    def from_path(path: pathlib.Path, id: int):
        ret = VideoEntity(**FileEntity.from_path(path).dict())
        ret.id = id
        return ret


class ImageEntity(FileEntity):
    durationInSecond: int = Field(default=0)

    @staticmethod
    def from_path(path: pathlib.Path, id: int):
        ret = VideoEntity(**FileEntity.from_path(path).dict())
        ret.id = id
        return ret


class LikeEntity(SQLModel, table=True):
    type: str = Field(primary_key=True)
    id: int = Field(primary_key=True)


class ViewHistoryEntity(SQLModel, table=True):
    type: str = Field(primary_key=True)
    id: int = Field(primary_key=True)
    updateTime: datetime | None = Field(default=None)


class ComicResponse(ComicEntity):
    lastViewedTime: datetime
    like: bool
