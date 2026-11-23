import asyncio
import time
from agents.base_agent import run_agent
from registry.registry import get_agents_for_skill, get_manifest
from reputation.scoring import pick_best_agent, update_score
from arbitration.engine import detect_conflict
from agents.research_tools import grounded_research

MAX_ATTEMPTS = 2
BACKOFF_SECONDS = 2


def is_infra_error(e: Exception) -> bool:
    """Rate limits, timeouts, and connection errors are not the agent's fault."""
    name = type(e).__name__.lower()
    msg = str(e).lower()
    infra_signals = ["ratelimit", "timeout", "timed out", "connection", "429", "503", "502", "providers exhausted"]
    return any(s in name or s in msg for s in infra_signals)

async def _call_agent(skill, prompt, manifest):
    if skill == "research" and getattr(manifest, "strategy", "plain") == "grounded":
        return await grounded_research(prompt, provider=manifest.provider, model=manifest.model)
    return await run_agent(skill, prompt, provider=manifest.provider, model=manifest.model)

async def _emit(emit, event_type, payload):
    if emit is None:
        return
    try:
        await emit(event_type, payload)
    except Exception as e:
        print(f"[EMIT ERROR] {event_type}: {e}")


async def run_node(node, state, query, meta, emit=None, forced_agents=None, instructions=None):
    node_id = node["id"]
    skill = node["agent"]
    started = time.time()
    await _emit(emit, "node_started", {"node_id": node_id, "skill": skill, "depends_on": node["depends_on"]})

    candidates = get_agents_for_skill(skill)
    if not candidates:
        meta[node_id] = {"status": "failed", "agent": None, "attempts": 0, "duration_s": 0,
                         "error": f"No registered agent for skill '{skill}'"}
        await _emit(emit, "node_failed", {"node_id": node_id, "skill": skill, **meta[node_id]})
        return

    context = "\n".join(f"{d}: {state[d]}" for d in node["depends_on"])
    prompt = node.get("forced_prompt") or (
        f"Task: {query}\nContext from previous agents:\n{context}" if context else f"Task: {query}"
    )
    if instructions and node_id in instructions:
        prompt += f"\n\nAdditional instruction from the user: {instructions[node_id]}"

    tried = []
    last_error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        forced = (forced_agents or {}).get(node_id)
        if forced and attempt == 1 and forced in candidates:
            pool = [forced]
        else:
            pool = [c for c in candidates if c not in tried] or candidates
        chosen = pick_best_agent(pool)
        print(f"[ROUTING] node={node_id} skill={skill} chose={chosen} attempt={attempt}")
        manifest = get_manifest(chosen)
        try:
            state[node_id] = await _call_agent(skill, prompt, manifest)
            update_score(chosen, success=True)
            meta[node_id] = {"status": "done", "agent": chosen, "attempts": attempt,
                             "duration_s": round(time.time() - started, 2), "error": None}
            await _emit(emit, "node_finished", {"node_id": node_id, "skill": skill,
                                                "output": state[node_id], **meta[node_id]})
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
                     "duration_s": round(time.time() - started, 2), "error": str(last_error)[:300]}
    await _emit(emit, "node_failed", {"node_id": node_id, "skill": skill, **meta[node_id]})


async def execute_plan(plan, query, emit=None, initial_state=None, forced_agents=None, instructions=None):
    state = dict(initial_state or {})
    reused = set(state)
    meta = {nid: {"status": "done", "agent": "reused", "attempts": 0, "duration_s": 0,
                  "error": None, "reused": True} for nid in state}
    conflicts = []
    remaining = [n for n in plan if n["id"] not in state]

    for n in plan:
        if n["id"] in reused:
            await _emit(emit, "node_finished", {
                "node_id": n["id"], "skill": n["agent"], "depends_on": n["depends_on"],
                "agent": "reused", "attempts": 0, "duration_s": 0, "error": None,
                "output": state[n["id"]], "reused": True})

    while remaining:
        for n in list(remaining):
            bad = [d for d in n["depends_on"] if meta.get(d, {}).get("status") in ("failed", "skipped")]
            if bad:
                meta[n["id"]] = {"status": "skipped", "agent": None, "attempts": 0, "duration_s": 0,
                                 "error": f"Skipped because upstream node(s) {bad} did not complete"}
                await _emit(emit, "node_skipped", {"node_id": n["id"], "skill": n["agent"],
                                                   "depends_on": n["depends_on"], **meta[n["id"]]})
                remaining.remove(n)

        ready = [n for n in remaining if all(d in state for d in n["depends_on"])]
        if not ready:
            if remaining:
                raise RuntimeError(f"Deadlock: {remaining}")
            break

        await asyncio.gather(*(run_node(n, state, query, meta, emit, forced_agents, instructions) for n in ready))
        remaining = [n for n in remaining if n["id"] not in meta]

    ids = list(state.keys())
    pairs = [(ids[i], ids[j]) for i in range(len(ids)) for j in range(i + 1, len(ids))
        if not (ids[i] in reused and ids[j] in reused)]
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
            await _emit(emit, "conflict_found", {"between": [a, b], **conflict})

    all_ok = all(m["status"] == "done" for m in meta.values())
    status = "complete" if all_ok else ("partial" if state else "failed")
    await _emit(emit, "run_finished", {"status": status})
    return {"outputs": state, "conflicts": conflicts, "node_status": meta, "status": status}