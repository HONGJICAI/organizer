from sqlmodel import SQLModel, create_engine

import model

engine = create_engine("sqlite:///prod.sqlite", echo=False)
SQLModel.metadata.create_all(engine)
