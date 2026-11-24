"""Append-only, hash-chained audit log.

Each entry stores the hash of the previous entry; hash = sha256(prev_hash + canonical JSON of the
entry). The database blocks UPDATE and DELETE (triggers in db/database.py), and verify_chain()
detects any change made by going around them (e.g. a superuser disabling the trigger).
"""
import hashlib
import json
import threading

from sqlalchemy import select

from db.database import SessionLocal
from db.models import AuditEntry

GENESIS = "0" * 64
_lock = threading.Lock()


def _digest(prev_hash: str, actor: str, action: str, target: str, detail: dict) -> str:
    body = json.dumps({"actor": actor, "action": action, "target": target, "detail": detail},
                      sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256((prev_hash + body).encode()).hexdigest()


def record(actor: str, action: str, target: str = "", detail: dict | None = None) -> dict:
    """Append one entry. Never raises into the caller's main work: failures are printed."""
    detail = detail or {}
    try:
        with _lock, SessionLocal() as s:
            last = s.scalar(select(AuditEntry).order_by(AuditEntry.id.desc()).limit(1))
            prev = last.hash if last else GENESIS
            entry = AuditEntry(actor=str(actor)[:120], action=action[:60], target=str(target)[:200],
                               detail=detail, prev_hash=prev,
                               hash=_digest(prev, str(actor)[:120], action[:60], str(target)[:200], detail))
            s.add(entry)
            s.commit()
            return {"id": entry.id, "hash": entry.hash}
    except Exception as e:
        print(f"[AUDIT] failed to record {action}: {type(e).__name__}: {e}")
        return {}


def entries(limit: int = 200, action: str | None = None) -> list:
    with SessionLocal() as s:
        q = select(AuditEntry).order_by(AuditEntry.id.desc()).limit(limit)
        if action:
            q = q.where(AuditEntry.action == action)
        rows = s.scalars(q).all()
    return [{"id": e.id, "created_at": e.created_at.isoformat(), "actor": e.actor, "action": e.action,
             "target": e.target, "detail": e.detail, "hash": e.hash[:12]} for e in rows]


def verify_chain() -> dict:
    with SessionLocal() as s:
        rows = s.scalars(select(AuditEntry).order_by(AuditEntry.id)).all()
    prev = GENESIS
    for e in rows:
        if e.prev_hash != prev or e.hash != _digest(prev, e.actor, e.action, e.target, e.detail):
            return {"ok": False, "entries": len(rows), "broken_at": e.id}
        prev = e.hash
    return {"ok": True, "entries": len(rows), "head": prev[:12]}
