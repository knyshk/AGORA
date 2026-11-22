import time
from datetime import datetime, timezone
from sqlalchemy import select
from db.database import SessionLocal
from db.models import Run, NodeRun, RunEvent


def create_run(query: str, mode: str = "isolated", parent_run_id: str = None) -> str:
    with SessionLocal() as s:
        run = Run(query=query, mode=mode, status="running", parent_run_id=parent_run_id)
        s.add(run)
        s.commit()
        return run.id


def finish_run(run_id: str, plan: list, status: str, conflicts: list, started: float):
    with SessionLocal() as s:
        run = s.get(Run, run_id)
        run.plan = plan
        run.status = status
        run.conflicts = conflicts
        run.finished_at = datetime.now(timezone.utc)
        run.duration_s = round(time.time() - started, 2)
        s.commit()


def list_runs(limit: int = 50):
    with SessionLocal() as s:
        rows = s.scalars(select(Run).order_by(Run.created_at.desc()).limit(limit)).all()
        return [
            {"id": r.id, "query": r.query, "mode": r.mode, "status": r.status,
             "duration_s": r.duration_s, "created_at": r.created_at.isoformat(),
             "conflict_count": len(r.conflicts or []), "parent_run_id": r.parent_run_id}
            for r in rows
        ]


def get_run(run_id: str):
    with SessionLocal() as s:
        run = s.get(Run, run_id)
        if not run:
            return None
        nodes = s.scalars(select(NodeRun).where(NodeRun.run_id == run_id).order_by(NodeRun.id)).all()
        events = s.scalars(select(RunEvent).where(RunEvent.run_id == run_id).order_by(RunEvent.seq)).all()
        return {
            "run": {"id": run.id, "query": run.query, "mode": run.mode, "status": run.status,
                    "plan": run.plan, "conflicts": run.conflicts, "duration_s": run.duration_s,
                    "created_at": run.created_at.isoformat(), "parent_run_id": run.parent_run_id},
            "nodes": [{"node_id": n.node_id, "skill": n.skill, "agent": n.agent_name, "status": n.status,
                       "attempts": n.attempts, "duration_s": n.duration_s, "error": n.error,
                       "output": n.output, "depends_on": n.depends_on} for n in nodes],
            "events": [{"seq": e.seq, "type": e.type, "payload": e.payload,
                        "created_at": e.created_at.isoformat()} for e in events],
        }