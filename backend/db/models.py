import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Text, Integer, Float, DateTime, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column
from db.database import Base


def _now():
    return datetime.now(timezone.utc)


def _uuid():
    return uuid.uuid4().hex


class Run(Base):
    __tablename__ = "runs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    query: Mapped[str] = mapped_column(Text)
    mode: Mapped[str] = mapped_column(String(20), default="isolated")
    status: Mapped[str] = mapped_column(String(20), default="running")
    plan: Mapped[list] = mapped_column(JSON, default=list)
    conflicts: Mapped[list] = mapped_column(JSON, default=list)
    parent_run_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_s: Mapped[float | None] = mapped_column(Float, nullable=True)


class NodeRun(Base):
    __tablename__ = "node_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    node_id: Mapped[str] = mapped_column(String(32))
    skill: Mapped[str] = mapped_column(String(32))
    agent_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="running")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    duration_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    output: Mapped[str | None] = mapped_column(Text, nullable=True)
    depends_on: Mapped[list] = mapped_column(JSON, default=list)


class RunEvent(Base):
    __tablename__ = "run_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

# ---------------- live collaboration ----------------

class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(80))
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class CollabSession(Base):
    """A workspace for runs. mode 'isolated' = owner only; 'collaborative' = members join and watch live.
    Upgrading isolated -> collaborative keeps every run and event."""
    __tablename__ = "collab_sessions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String(200))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    mode: Mapped[str] = mapped_column(String(20), default="isolated")
    editor_token: Mapped[str] = mapped_column(String(32), default=_uuid, index=True)
    viewer_token: Mapped[str] = mapped_column(String(32), default=_uuid, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class SessionMember(Base):
    __tablename__ = "session_members"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("collab_sessions.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(10))          # owner | editor | viewer
    last_seen_event_id: Mapped[int] = mapped_column(Integer, default=0)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class SessionRun(Base):
    """Links runs to a session (a link table, so the existing runs table needs no migration)."""
    __tablename__ = "session_runs"
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("collab_sessions.id"), index=True)
