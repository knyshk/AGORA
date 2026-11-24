"""Alembic environment: models from db.models, URL from DATABASE_URL (same as the app)."""
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

from db.database import DATABASE_URL, Base
from db import models  # noqa: F401  (registers the tables)

if context.config.config_file_name:
    fileConfig(context.config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def run_migrations_offline():
    context.configure(url=DATABASE_URL, target_metadata=target_metadata, literal_binds=True,
                      render_as_batch=DATABASE_URL.startswith("sqlite"))
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    given = context.config.attributes.get("connection")  # init_db passes its own connection
    if given is not None:
        _run(given)
        return
    with create_engine(DATABASE_URL).connect() as connection:
        _run(connection)


def _run(connection):
    context.configure(connection=connection, target_metadata=target_metadata,
                      render_as_batch=connection.dialect.name == "sqlite", compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
