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
            _protect_audit_log()
            return
        except Exception as e:
            print(f"[DB] not ready ({attempt + 1}/{retries}): {type(e).__name__}")
            time.sleep(1)
    raise RuntimeError("Database never became ready")

def _protect_audit_log():
    """Make audit_log append-only at the database level."""
    from sqlalchemy import text
    with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            conn.execute(text(
                "CREATE OR REPLACE FUNCTION audit_log_append_only() RETURNS trigger AS $$ "
                "BEGIN RAISE EXCEPTION 'audit_log is append-only'; END; $$ LANGUAGE plpgsql"))
            conn.execute(text("DROP TRIGGER IF EXISTS audit_log_no_change ON audit_log"))
            conn.execute(text("CREATE TRIGGER audit_log_no_change BEFORE UPDATE OR DELETE ON audit_log "
                              "FOR EACH ROW EXECUTE FUNCTION audit_log_append_only()"))
        elif engine.dialect.name == "sqlite":
            for op in ("UPDATE", "DELETE"):
                conn.execute(text(f"CREATE TRIGGER IF NOT EXISTS audit_log_no_{op.lower()} BEFORE {op} ON audit_log "
                                  "BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END"))
