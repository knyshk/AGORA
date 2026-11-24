"""Observability: aggregate the stored runs, event log, conflicts, reputation history and audit log.

Everything is computed from data AGORA already records (Postgres event log + Redis scores), so the
dashboard can never show a number that is not backed by stored events.
"""
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from db.database import SessionLocal
from db.models import AuditEntry, Run, RunEvent
from registry.registry import REGISTRY
from reputation.scoring import get_stats
from security.audit import verify_chain

EVENT_TYPES = ("node_finished", "node_failed", "node_attempt_failed", "reputation_updated",
               "node_takeover_waiting", "conflict_resolved", "run_finished")
MAX_POINTS_PER_AGENT = 200


def _load(days: int):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    with SessionLocal() as s:
        runs = s.scalars(select(Run).where(Run.created_at >= since).order_by(Run.created_at)).all()
        ids = [r.id for r in runs]
        events = s.scalars(select(RunEvent).where(RunEvent.run_id.in_(ids), RunEvent.type.in_(EVENT_TYPES))
                           .order_by(RunEvent.id)).all() if ids else []
        audit_counts = dict(s.execute(select(AuditEntry.action, func.count()).group_by(AuditEntry.action)).all())
    return runs, events, audit_counts


def _mean(values):
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 3) if values else None


def agent_stats(events) -> list:
    per = defaultdict(lambda: {"done": 0, "failed": 0, "infra_failures": 0, "quality_failures": 0,
                               "durations": [], "qualities": [], "cost": 0.0, "tokens": 0, "calls": 0,
                               "with_usage": 0})
    for e in events:
        p = e.payload
        agent = p.get("agent")
        if not agent or agent == "reused" or str(agent).startswith("human:"):
            continue
        a = per[agent]
        if e.type in ("node_finished", "node_failed"):
            a["done" if e.type == "node_finished" else "failed"] += 1
            a["durations"].append(p.get("duration_s"))
            if e.type == "node_finished":
                a["qualities"].append(p.get("quality"))
            u = p.get("usage") or {}
            a["with_usage"] += 1 if u else 0
            a["cost"] += u.get("cost_usd", 0.0)
            a["tokens"] += u.get("tokens_in", 0) + u.get("tokens_out", 0)
            a["calls"] += u.get("llm_calls", 0)
        elif e.type == "node_attempt_failed":
            a["infra_failures" if p.get("infra") else "quality_failures"] += 1
    out = []
    for name in sorted(set(REGISTRY) | set(per)):
        a = per[name]
        m = REGISTRY.get(name)
        total = a["done"] + a["failed"]
        st = get_stats(name) if m else {}
        out.append({"agent": name, "skill": m.skill if m else "?", "model": m.model if m else "?",
                    "nodes": total, "done": a["done"], "failed": a["failed"],
                    "success_rate": round(a["done"] / total, 3) if total else None,
                    "infra_failures": a["infra_failures"], "quality_failures": a["quality_failures"],
                    "avg_duration_s": _mean(a["durations"]), "avg_quality": _mean(a["qualities"]),
                    "cost_usd": round(a["cost"], 6), "tokens": a["tokens"], "llm_calls": a["calls"],
                    # nodes from before usage tracking have unknown (not zero) cost
                    "nodes_with_usage": a["with_usage"],
                    "cost_per_node_usd": round(a["cost"] / a["with_usage"], 6) if a["with_usage"] else None,
                    "trust_mean": st.get("mean"), "trust_ci95": st.get("ci95"), "graded_runs": st.get("n")})
    return out


def reputation_series(events) -> dict:
    series = defaultdict(list)
    for e in events:
        if e.type != "reputation_updated":
            continue
        p = e.payload
        after = p.get("after") or {}
        if p.get("agent") and after.get("mean") is not None:
            series[p["agent"]].append({"t": e.created_at.isoformat(), "trust": after["mean"],
                                       "quality": p.get("quality"), "source": p.get("source")})
    return {a: pts[-MAX_POINTS_PER_AGENT:] for a, pts in series.items()}


def run_stats(runs, events) -> dict:
    cost_by_run = {e.run_id: (e.payload.get("usage") or {}).get("total", {}).get("cost_usd")
                   for e in events if e.type == "run_finished"}
    per_day = defaultdict(Counter)
    for r in runs:
        per_day[r.created_at.date().isoformat()][r.status] += 1
    finished = [r for r in runs if r.status not in ("running", "planned")]
    statuses = Counter(r.status for r in runs)
    return {"total": len(runs), "by_status": dict(statuses),
            "success_rate": round(statuses["complete"] / len(finished), 3) if finished else None,
            "avg_duration_s": _mean([r.duration_s for r in finished]),
            "forks": sum(1 for r in runs if r.parent_run_id),
            "cost_usd": round(sum(c for c in cost_by_run.values() if c), 6),
            "runs_with_cost": sum(1 for c in cost_by_run.values() if c is not None),
            "per_day": [{"day": d, **dict(c)} for d, c in sorted(per_day.items())]}


def conflict_stats(runs) -> dict:
    structured = [c for r in runs for c in (r.conflicts or []) if isinstance(c, dict) and "status" in c]
    legacy = sum(1 for r in runs for c in (r.conflicts or []) if isinstance(c, dict) and "status" not in c)
    resolved = [c for c in structured if c["status"] == "resolved"]
    agreed = [c for c in resolved if (c.get("resolution") or {}).get("agreed_with_recommendation")]
    finished = [r for r in runs if r.status not in ("running", "planned")]
    with_conflicts = [r for r in finished if r.conflicts]
    return {"total": len(structured), "open": sum(1 for c in structured if c["status"] == "open"),
            "resolved": len(resolved), "legacy_pairwise": legacy,
            "by_policy": dict(Counter(c.get("policy") for c in structured)),
            "reviewer_agreed_with_recommendation": len(agreed),
            "runs_with_conflicts": len(with_conflicts),
            "conflict_rate": round(len(with_conflicts) / len(finished), 3) if finished else None}


def overview(days: int = 30) -> dict:
    runs, events, audit_counts = _load(days)
    human_nodes = sum(1 for e in events if e.type == "node_finished" and str(e.payload.get("agent", "")).startswith("human:"))
    return {"window_days": days, "generated_at": datetime.now(timezone.utc).isoformat(),
            "runs": run_stats(runs, events), "agents": agent_stats(events),
            "reputation": reputation_series(events), "conflicts": conflict_stats(runs),
            "humans": {"takeovers": sum(1 for e in events if e.type == "node_takeover_waiting"),
                       "nodes_written_by_people": human_nodes,
                       "conflict_decisions": sum(1 for e in events if e.type == "conflict_resolved")},
            "audit": {**verify_chain(), "by_action": audit_counts},
            "pricing": "notional (free tiers actually charge $0)"}
