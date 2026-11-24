from sqlalchemy import func, select
from db.database import SessionLocal
from db.models import NodeRun, RunEvent

NODE_EVENTS = {"node_started", "node_finished", "node_failed", "node_skipped"}


class RunRecorder:
    """Passed to the executor as `emit`. Stores every event and keeps node rows up to date."""

    def __init__(self, run_id: str, on_event=None):
        self.run_id = run_id
        self.seq = 0
        self.on_event = on_event  # e.g. live broadcast to a collaborative session

    @classmethod
    def resume(cls, run_id: str, on_event=None) -> "RunRecorder":
        """Continue an existing run's event log (e.g. a reviewer resolving a conflict later)."""
        rec = cls(run_id, on_event)
        with SessionLocal() as s:
            rec.seq = s.scalar(select(func.max(RunEvent.seq)).where(RunEvent.run_id == run_id)) or 0
        return rec

    async def __call__(self, event_type: str, payload: dict):
        self.seq += 1
        with SessionLocal() as s:
            event = RunEvent(run_id=self.run_id, seq=self.seq, type=event_type, payload=payload)
            s.add(event)
            if event_type in NODE_EVENTS:
                node = s.scalar(select(NodeRun).where(
                    NodeRun.run_id == self.run_id, NodeRun.node_id == payload["node_id"]))
                if node is None:
                    node = NodeRun(run_id=self.run_id, node_id=payload["node_id"],
                                   skill=payload.get("skill", ""), depends_on=payload.get("depends_on", []))
                    s.add(node)
                node.status = {"node_started": "running", "node_finished": "done",
                               "node_failed": "failed", "node_skipped": "skipped"}[event_type]
                for field in ("agent", "attempts", "duration_s", "error", "output"):
                    if field in payload:
                        setattr(node, "agent_name" if field == "agent" else field, payload[field])
            s.commit()
            stored = {"id": event.id, "run_id": self.run_id, "seq": self.seq, "type": event_type, "payload": payload}
        if self.on_event:
            try:
                await self.on_event(stored)
            except Exception as e:
                print(f"[LIVE] broadcast failed: {type(e).__name__}: {e}")