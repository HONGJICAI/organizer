import os
from typing import Generator
from sqlmodel import SQLModel, create_engine, Session

import model

_db_path = os.environ.get("DB_PATH", "prod.sqlite")
engine = create_engine(f"sqlite:///{_db_path}", echo=False)
SQLModel.metadata.create_all(engine)


def _ensure_column(table: str, column: str, ddl: str) -> None:
    """Add a column to an existing table if it's missing.

    SQLModel's ``create_all`` only creates absent tables — it never ALTERs an
    existing one — and the project has no migration framework. This idempotent
    guard backfills new columns on a pre-existing ``prod.sqlite`` so adding a
    field to a model doesn't break deployed databases. SQLite supports
    ``ADD COLUMN`` with a literal DEFAULT, which also fills existing rows.
    """
    with engine.connect() as conn:
        existing = {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")}
        if column not in existing:
            conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {ddl}")
            conn.commit()


# Backfill columns added after the initial schema (see model.FileEntity).
_ensure_column("comicentity", "missing", "missing BOOLEAN NOT NULL DEFAULT 0")
_ensure_column("videoentity", "missing", "missing BOOLEAN NOT NULL DEFAULT 0")


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
