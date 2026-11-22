import os
import time
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg2://agora:agora@postgres:5432/agora")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def init_db(retries: int = 15):
    from db import models  # noqa: F401  (registers the tables)
    for attempt in range(retries):
        try:
            Base.metadata.create_all(engine)
            return
        except Exception as e:
            print(f"[DB] not ready ({attempt + 1}/{retries}): {type(e).__name__}")
            time.sleep(1)
    raise RuntimeError("Database never became ready")