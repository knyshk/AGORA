import asyncio
import time
from agents.base_agent import run_agent
from registry.registry import get_agents_for_skill, get_manifest
from reputation.scoring import pick_best_agent, update_score
from arbitration.engine import detect_conflict

MAX_ATTEMPTS = 2
BACKOFF_SECONDS = 2


def is_infra_error(e: Exception) -> bool:
    """Rate limits, timeouts, and connection errors are not the agent's fault."""
    name = type(e).__name__.lower()
    msg = str(e).lower()
    infra_signals = ["ratelimit", "timeout", "timed out", "connection", "429", "503", "502", "providers exhausted"]
    return any(s in name or s in msg for s in infra_signals)


async def run_node(node, state, query, meta):
    node_id = node["id"]
    started = time.time()
    candidates = get_agents_for_skill(node["agent"])
    if not candidates:
        meta[node_id] = {"status": "failed", "agent": None, "attempts": 0,
                         "duration_s": 0, "error": f"No registered agent for skill '{node['agent']}'"}
        return

    context = "\n".join(f"{d}: {state[d]}" for d in node["depends_on"])
    prompt = node.get("forced_prompt") or (
        f"Task: {query}\nContext from previous agents:\n{context}" if context else f"Task: {query}"
    )

    tried = []
    last_error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        pool = [c for c in candidates if c not in tried] or candidates
        chosen = pick_best_agent(pool)
        print(f"[ROUTING] node={node_id} skill={node['agent']} chose={chosen} attempt={attempt}")
        manifest = get_manifest(chosen)
        try:
            state[node_id] = await run_agent(node["agent"], prompt,
                                             provider=manifest.provider, model=manifest.model)
            update_score(chosen, success=True)
            meta[node_id] = {"status": "done", "agent": chosen, "attempts": attempt,
                             "duration_s": round(time.time() - started, 2), "error": None}
            return
        except Exception as e:
            last_error = e
            tried.append(chosen)
            if is_infra_error(e):
                print(f"[INFRA ERROR] {chosen}: {e} (not counted against reputation)")
            else:
                update_score(chosen, success=False)
            if attempt < MAX_ATTEMPTS:
                await asyncio.sleep(BACKOFF_SECONDS * attempt)

    meta[node_id] = {"status": "failed", "agent": tried[-1], "attempts": len(tried),
                     "duration_s": round(time.time() - started, 2),
                     "error": str(last_error)[:300]}


async def execute_plan(plan, query):
    state = {}
    meta = {}
    conflicts = []
    remaining = plan.copy()

    while remaining:
        # Skip nodes whose upstream dependency failed or was skipped
        for n in list(remaining):
            bad = [d for d in n["depends_on"] if meta.get(d, {}).get("status") in ("failed", "skipped")]
            if bad:
                meta[n["id"]] = {"status": "skipped", "agent": None, "attempts": 0, "duration_s": 0,
                                 "error": f"Skipped because upstream node(s) {bad} did not complete"}
                remaining.remove(n)

        ready = [n for n in remaining if all(d in state for d in n["depends_on"])]
        if not ready:
            if remaining:
                raise RuntimeError(f"Deadlock: {remaining}")
            break

        await asyncio.gather(*(run_node(n, state, query, meta) for n in ready))
        remaining = [n for n in remaining if n["id"] not in meta]

    # Conflict detection only between nodes that finished
    ids = list(state.keys())
    pairs = [(ids[i], ids[j]) for i in range(len(ids)) for j in range(i + 1, len(ids))]
    results = await asyncio.gather(
        *(detect_conflict(state[a], state[b], label_a=a, label_b=b) for a, b in pairs),
        return_exceptions=True,
    )
    for (a, b), conflict in zip(pairs, results):
        if isinstance(conflict, Exception):
            print(f"[ARBITRATION ERROR] {a} vs {b}: {conflict}")
            continue
        if conflict:
            conflicts.append({"between": [a, b], **conflict})
            print(f"[CONFLICT] {a} vs {b}: {conflict['explanation']}")

    all_ok = all(m["status"] == "done" for m in meta.values())
    status = "complete" if all_ok else ("partial" if state else "failed")
    return {"outputs": state, "conflicts": conflicts, "node_status": meta, "status": status}