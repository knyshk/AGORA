"""Structured arbitration: compare claims field by field instead of asking an LLM about whole texts.

1. Claims from every node are grouped by (entity, attribute, period, kind of unit).
2. Inside a group, values are clustered deterministically: two claims agree when they differ by no
   more than the rounding of the less precise one plus REL_TOLERANCE ("about $97 billion" agrees
   with "$96.77 billion"; "$97.69 billion" does not).
3. A group with more than one cluster from DIFFERENT nodes is a conflict.
4. Resolution policy ranks the sides by source authority (official filing > official site >
   encyclopedia > other web > uncited) and by the reputation of the agents that stated them, and
   recommends one. A human decides (approval gate); the decision updates reputation.
Cost: one LLM call per text node instead of one per pair of nodes.
"""
import asyncio
import re

from arbitration.claims import extract_claims
from reputation.scoring import get_stats

REL_TOLERANCE = 1e-6  # float noise only; rounding is handled by each claim's written precision
AUTHORITY_WEIGHT = 0.7
TRUST_WEIGHT = 0.3
CLEAR_AUTHORITY_GAP = 0.3


def source_authority(url: str) -> tuple:
    u = (url or "").lower()
    if "sec.gov" in u:
        return 1.0, "official regulatory filing (SEC EDGAR)"
    if re.search(r"\.gov(\.|/|$)|\bir\.|investor|annualreport|annual-report", u):
        return 0.85, "official government or company source"
    if "wikipedia.org" in u:
        return 0.6, "encyclopedia (Wikipedia)"
    return 0.5, "other web source"


def claim_authority(claim: dict, skill: str) -> tuple:
    if claim["sources"]:
        return max((source_authority(s["url"]) for s in claim["sources"]), key=lambda x: x[0])
    if skill == "chart":
        return 0.4, "chart value derived from upstream research"
    return 0.2, "no cited source"


def agree(a: dict, b: dict) -> bool:
    tol = max(a["precision"], b["precision"]) + REL_TOLERANCE * max(abs(a["absolute"]), abs(b["absolute"]))
    return abs(a["absolute"] - b["absolute"]) <= tol


def cluster(claims: list) -> list:
    clusters = []
    for c in sorted(claims, key=lambda x: x["precision"]):  # most precise claim anchors each cluster
        home = next((cl for cl in clusters if agree(cl[0], c)), None)
        if home:
            home.append(c)
        else:
            clusters.append([c])
    return clusters


def group_key(c: dict) -> tuple:
    return (c["entity"], c["attribute"], c["period"], c["kind"])


def fmt_value(c: dict) -> str:
    unit = c["unit"]
    money = unit.upper() in ("USD", "$")
    scale = f" {c['scale']}" if c["scale"] else ""
    number = f"{c['value']:,}".rstrip("0").rstrip(".") if isinstance(c["value"], float) else f"{c['value']:,}"
    if money:
        return f"${number}{scale}"
    return f"{number}{scale} {unit}".strip()


def build_side(claims: list, skills: dict) -> dict:
    best = max(claims, key=lambda c: claim_authority(c, skills.get(c["node_id"], ""))[0])
    authority, why = claim_authority(best, skills.get(best["node_id"], ""))
    agents = sorted({c["agent"] for c in claims if c["agent"]})
    trust = max((get_stats(a)["mean"] for a in agents), default=0.5)
    return {"value": fmt_value(best), "absolute": best["absolute"],
            "nodes": sorted({c["node_id"] for c in claims}), "agents": agents,
            "authority": authority, "authority_reason": why, "trust": round(trust, 3),
            "score": round(AUTHORITY_WEIGHT * authority + TRUST_WEIGHT * trust, 3),
            "claims": [{k: c[k] for k in ("node_id", "agent", "quote", "sources")} for c in claims]}


def build_conflict(cid: str, key: tuple, clusters: list, skills: dict) -> dict:
    sides = sorted((build_side(cl, skills) for cl in clusters), key=lambda s: s["score"], reverse=True)
    top, runner = sides[0], sides[1]
    entity, attribute, period, _ = key
    label = f"{clusters[0][0]['entity_display']} {attribute}" + (f" ({period})" if period else "")
    if top["authority"] - runner["authority"] >= CLEAR_AUTHORITY_GAP:
        policy = "source authority"
        why = f"{top['authority_reason']} outranks {runner['authority_reason']}"
    else:
        policy = "trust-weighted vote"
        why = f"similar source authority; higher combined authority x agent trust ({top['score']} vs {runner['score']})"
    statements = "; ".join(f"node {'/'.join(s['nodes'])} says {s['value']} ({s['authority_reason']})" for s in sides)
    gap = abs(top["absolute"] - runner["absolute"]) / max(abs(top["absolute"]), abs(runner["absolute"]), 1e-12)
    return {
        "id": cid, "between": sorted({n for s in sides for n in s["nodes"]}),
        "entity": entity, "attribute": attribute, "period": period, "label": label,
        "sides": sides, "recommended": 0, "policy": policy, "status": "open",
        "explanation": f"{label}: {statements}. The values differ by {gap:.1%}.",
        "suggested_resolution": f"Use {top['value']} — {why}.",
    }


def find_conflicts(claims: list, skills: dict) -> list:
    groups = {}
    for c in claims:
        if c["entity"] and c["attribute"]:
            groups.setdefault(group_key(c), []).append(c)
    conflicts = []
    for key, items in groups.items():
        if len({c["node_id"] for c in items}) < 2:
            continue  # disagreement inside one node is not an inter-agent conflict
        clusters = cluster(items)
        if len(clusters) < 2:
            continue
        nodes_per_cluster = [{c["node_id"] for c in cl} for cl in clusters]
        if len(set().union(*nodes_per_cluster)) < 2:
            continue
        conflicts.append(build_conflict(f"c{len(conflicts) + 1}", key, clusters, skills))
    return conflicts


async def arbitrate(outputs: dict, skills: dict, agents: dict, emit=None) -> list:
    """outputs/skills/agents: node_id -> output text / skill / agent name."""
    nodes = list(outputs)
    results = await asyncio.gather(
        *(extract_claims(n, skills.get(n, ""), agents.get(n, ""), outputs[n]) for n in nodes),
        return_exceptions=True)
    claims = []
    for node, res in zip(nodes, results):
        if isinstance(res, Exception):
            print(f"[ARBITRATION] claim extraction failed for {node}: {type(res).__name__}: {res}")
            if emit:
                await emit("arbitration_error", {"node_id": node, "error": f"{type(res).__name__}: {str(res)[:200]}"})
            continue
        claims += res
        if emit and res:
            await emit("claims_extracted", {"node_id": node, "count": len(res),
                                            "claims": [{k: c[k] for k in ("entity", "attribute", "period", "value",
                                                                          "scale", "unit", "quote")} for c in res]})
    return find_conflicts(claims, skills)
