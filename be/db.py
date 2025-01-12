from sqlmodel import SQLModel, create_engine, Session

import model

engine = create_engine("sqlite:///prod.sqlite", echo=False)
SQLModel.metadata.create_all(engine)


def get_session():
    return Session(engine)
