import os
from typing import Generator

from sqlalchemy import URL, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    """Base class inherited by all SQLAlchemy models."""

    pass


def build_database_url():
    """
    Build a PostgreSQL connection URL.

    Docker Compose supplies POSTGRES_HOST=postgres.
    Running directly on the host uses 127.0.0.1 by default.
    """

    explicit_url = os.getenv("DATABASE_URL")

    if explicit_url:
        if explicit_url.startswith("postgresql://"):
            explicit_url = explicit_url.replace(
                "postgresql://",
                "postgresql+psycopg://",
                1,
            )

        return explicit_url

    password = os.getenv("POSTGRES_PASSWORD")

    if not password:
        raise RuntimeError(
            "POSTGRES_PASSWORD is missing. "
            "Configure it in the local environment."
        )

    return URL.create(
        drivername="postgresql+psycopg",
        username=os.getenv("POSTGRES_USER", "agora"),
        password=password,
        host=os.getenv("POSTGRES_HOST", "127.0.0.1"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        database=os.getenv("POSTGRES_DB", "agora"),
    )


DATABASE_URL = build_database_url()


engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=5,
    pool_recycle=1800,
)


SessionLocal = sessionmaker(
    bind=engine,
    class_=Session,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI database dependency.

    Each request gets its own database session.
    The session is always closed after the request.
    """

    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


def check_database_connection() -> bool:
    """Check whether PostgreSQL is reachable."""

    from sqlalchemy import text

    with engine.connect() as connection:
        return connection.scalar(text("SELECT 1")) == 1
