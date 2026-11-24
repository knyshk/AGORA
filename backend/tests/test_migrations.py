"""The Alembic migrations must build exactly the schema the models describe."""
import tempfile
from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, text

from db.database import Base
from db import models  # noqa: F401


def test_migrations_match_models_and_protect_audit_log():
    with tempfile.TemporaryDirectory() as tmp:
        engine = create_engine(f"sqlite:///{tmp}/m.db")
        cfg = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
        with engine.begin() as conn:
            cfg.attributes["connection"] = conn
            command.upgrade(cfg, "head")
        with engine.connect() as conn:
            diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
        assert diff == [], f"models and migrations differ: {diff}"
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO audit_log (created_at, actor, action, target, detail, prev_hash, hash) "
                              "VALUES (CURRENT_TIMESTAMP, 'a', 'b', '', '{}', 'x', 'y')"))
        try:
            with engine.begin() as conn:
                conn.execute(text("DELETE FROM audit_log"))
            raise AssertionError("audit_log delete was allowed")
        except Exception as e:
            assert "append-only" in str(e)
