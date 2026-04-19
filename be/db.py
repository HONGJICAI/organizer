import os
from typing import Generator
from sqlmodel import SQLModel, create_engine, Session

import model

_db_path = os.environ.get("DB_PATH", "prod.sqlite")
engine = create_engine(f"sqlite:///{_db_path}", echo=False)
SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
