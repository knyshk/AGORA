"""Sessions, members and roles (database side of live collaboration)."""
from fastapi import HTTPException
from sqlalchemy import select

from db.database import SessionLocal
from db.models import CollabSession, Run, RunEvent, SessionMember, SessionRun, User

ROLES = ("viewer", "editor", "owner")
MODES = ("isolated", "collaborative")


def rank(role: str) -> int:
    return ROLES.index(role) if role in ROLES else -1


def create_session(owner: User, title: str, mode: str = "isolated") -> CollabSession:
    if mode not in MODES:
        raise HTTPException(status_code=422, detail=f"mode must be one of {MODES}")
    with SessionLocal() as s:
        sess = CollabSession(title=(title or "Untitled session")[:200], owner_id=owner.id, mode=mode)
        s.add(sess)
        s.flush()
        s.add(SessionMember(session_id=sess.id, user_id=owner.id, role="owner"))
        s.commit()
        return sess


def get_session(session_id: str) -> CollabSession:
    with SessionLocal() as s:
        sess = s.get(CollabSession, session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    return sess


def member_role(session_id: str, user_id: str) -> str | None:
    with SessionLocal() as s:
        m = s.scalar(select(SessionMember).where(SessionMember.session_id == session_id,
                                                 SessionMember.user_id == user_id))
    return m.role if m else None


def require_role(session_id: str, user: User, minimum: str) -> tuple:
    """Returns (session, role). Isolated sessions are visible to the owner only."""
    sess = get_session(session_id)
    role = member_role(session_id, user.id)
    if role is None or (sess.mode == "isolated" and role != "owner"):
        raise HTTPException(status_code=403, detail="You are not a member of this session")
    if rank(role) < rank(minimum):
        raise HTTPException(status_code=403, detail=f"This needs the '{minimum}' role (you are '{role}')")
    return sess, role


def join_with_token(user: User, token: str) -> tuple:
    with SessionLocal() as s:
        sess = s.scalar(select(CollabSession).where(
            (CollabSession.editor_token == token) | (CollabSession.viewer_token == token)))
        if not sess:
            raise HTTPException(status_code=404, detail="Invite link is not valid")
        if sess.mode != "collaborative":
            raise HTTPException(status_code=403, detail="This session is not open for collaboration")
        role = "editor" if token == sess.editor_token else "viewer"
        m = s.scalar(select(SessionMember).where(SessionMember.session_id == sess.id,
                                                 SessionMember.user_id == user.id))
        if m is None:
            s.add(SessionMember(session_id=sess.id, user_id=user.id, role=role))
        elif rank(role) > rank(m.role):
            m.role = role  # an editor link upgrades a viewer; never downgrades
        s.commit()
        return sess, (m.role if m else role)


def set_mode(session_id: str, mode: str) -> CollabSession:
    if mode not in MODES:
        raise HTTPException(status_code=422, detail=f"mode must be one of {MODES}")
    with SessionLocal() as s:
        sess = s.get(CollabSession, session_id)
        sess.mode = mode
        s.commit()
        return sess


def set_member_role(session_id: str, user_id: str, role: str):
    if role not in ("viewer", "editor"):
        raise HTTPException(status_code=422, detail="role must be viewer or editor")
    with SessionLocal() as s:
        m = s.scalar(select(SessionMember).where(SessionMember.session_id == session_id,
                                                 SessionMember.user_id == user_id))
        if not m or m.role == "owner":
            raise HTTPException(status_code=404, detail="No such member (the owner's role cannot change)")
        m.role = role
        s.commit()


def members(session_id: str) -> list:
    with SessionLocal() as s:
        rows = s.execute(select(SessionMember, User).join(User, User.id == SessionMember.user_id)
                         .where(SessionMember.session_id == session_id)).all()
    return [{"user_id": u.id, "name": u.name, "email": u.email, "role": m.role,
             "last_seen_event_id": m.last_seen_event_id} for m, u in rows]


def sessions_for(user: User) -> list:
    with SessionLocal() as s:
        rows = s.execute(select(CollabSession, SessionMember.role)
                         .join(SessionMember, SessionMember.session_id == CollabSession.id)
                         .where(SessionMember.user_id == user.id)
                         .order_by(CollabSession.created_at.desc())).all()
    return [{"id": c.id, "title": c.title, "mode": c.mode, "role": r} for c, r in rows]


def link_run(session_id: str, run_id: str):
    with SessionLocal() as s:
        s.add(SessionRun(session_id=session_id, run_id=run_id))
        s.commit()


def session_of_run(run_id: str) -> str | None:
    with SessionLocal() as s:
        link = s.get(SessionRun, run_id)
    return link.session_id if link else None


def runs_of(session_id: str) -> list:
    with SessionLocal() as s:
        rows = s.scalars(select(Run).join(SessionRun, SessionRun.run_id == Run.id)
                         .where(SessionRun.session_id == session_id).order_by(Run.created_at.desc())).all()
    return [{"id": r.id, "query": r.query, "status": r.status, "plan": r.plan,
             "created_at": r.created_at.isoformat()} for r in rows]


def events_since(session_id: str, after_id: int, limit: int = 300) -> list:
    """Events of all this session's runs with a global id greater than after_id, oldest first."""
    with SessionLocal() as s:
        rows = s.scalars(select(RunEvent).join(SessionRun, SessionRun.run_id == RunEvent.run_id)
                         .where(SessionRun.session_id == session_id, RunEvent.id > after_id)
                         .order_by(RunEvent.id).limit(limit)).all()
    return [{"id": e.id, "run_id": e.run_id, "seq": e.seq, "type": e.type, "payload": e.payload,
             "created_at": e.created_at.isoformat()} for e in rows]


def mark_seen(session_id: str, user_id: str, event_id: int):
    with SessionLocal() as s:
        m = s.scalar(select(SessionMember).where(SessionMember.session_id == session_id,
                                                 SessionMember.user_id == user_id))
        if m and event_id > m.last_seen_event_id:
            m.last_seen_event_id = event_id
            s.commit()
