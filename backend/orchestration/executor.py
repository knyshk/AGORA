import asyncio
import time
from agents.base_agent import run_agent
from registry.registry import get_agents_for_skill, get_manifest
from reputation.scoring import route, update_score
from reputation.quality import assess, draft_feedback
from arbitration.structured import arbitrate
from agents.research_tools import grounded_research
from agents.chart_tools import build_chart, strip_chart_blocks
from agents.drafting_tools import write_draft
from agents.factcheck_tools import fact_check

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
    if skill == "drafting" and getattr(manifest, "strategy", "plain") == "cited":
        return await write_draft(prompt, provider=manifest.provider, model=manifest.model)
    if skill == "fact_check" and getattr(manifest, "strategy", "plain") == "verify":
        return await fact_check(prompt, provider=manifest.provider, model=manifest.model)
    if skill == "chart" and getattr(manifest, "strategy", "plain") == "spec":
        return await build_chart(prompt, provider=manifest.provider, model=manifest.model)
    return await run_agent(skill, prompt, provider=manifest.provider, model=manifest.model)

async def _emit(emit, event_type, payload):
    if emit is None:
        return
    try:
        await emit(event_type, payload)
    except Exception as e:
        print(f"[EMIT ERROR] {event_type}: {e}")


async def _feedback_to_drafts(node, fact_check_output, meta, emit):
    """Fact-check verdicts are graded evidence about the drafting agent that wrote the claims."""
    feedback = draft_feedback(fact_check_output)
    if feedback is None:
        return
    quality, reason = feedback
    for dep in node["depends_on"]:
        agent = meta.get(dep, {}).get("agent")
        if not agent or agent == "reused":
            continue
        try:
            if get_manifest(agent).skill != "drafting":
                continue
        except KeyError:
            continue
        stats = update_score(agent, quality=quality)
        await _emit(emit, "reputation_updated", {"node_id": dep, "agent": agent, "skill": "drafting",
                                                 "quality": quality, "reason": reason,
                                                 "source": "fact_check_feedback", "after": stats})


async def _human_node(node, state, meta, emit, takeover, started) -> bool:
    """If a person has taken over this node, wait for their output. Returns True if they delivered it."""
    holder = takeover.holder(node["id"]) if takeover else None
    if not holder:
        return False
    node_id, skill = node["id"], node["agent"]
    await _emit(emit, "node_takeover_waiting", {"node_id": node_id, "skill": skill, "user": holder})
    output = await takeover.wait(node_id)
    if output is None:
        await _emit(emit, "node_takeover_released", {"node_id": node_id, "skill": skill, "user": holder})
        return False
    state[node_id] = output
    meta[node_id] = {"status": "done", "agent": f"human:{holder['name']}", "attempts": 1,
                     "duration_s": round(time.time() - started, 2), "error": None,
                     "quality": None, "quality_reason": "written by a person (not graded)", "human": holder}
    await _emit(emit, "node_finished", {"node_id": node_id, "skill": skill, "output": output, **meta[node_id]})
    return True


async def run_node(node, state, query, meta, emit=None, forced_agents=None, instructions=None, takeover=None):
    node_id = node["id"]
    skill = node["agent"]
    started = time.time()
    await _emit(emit, "node_started", {"node_id": node_id, "skill": skill, "depends_on": node["depends_on"]})
    if await _human_node(node, state, meta, emit, takeover, started):
        return
    if takeover:
        takeover.mark_started(node_id)

    candidates = get_agents_for_skill(skill)
    if not candidates:
        meta[node_id] = {"status": "failed", "agent": None, "attempts": 0, "duration_s": 0,
                         "error": f"No registered agent for skill '{skill}'"}
        await _emit(emit, "node_failed", {"node_id": node_id, "skill": skill, **meta[node_id]})
        return

    context = "\n".join(f"{d}: {strip_chart_blocks(state[d])}" for d in node["depends_on"])
    prompt = node.get("forced_prompt") or (
        f"Task: {query}\nContext from previous agents:\n{context}" if context else f"Task: {query}"
    )
    if instructions and node_id in instructions:
        prompt += f"\n\nAdditional instruction from the user: {instructions[node_id]}"

    tried = []
    last_error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        forced = (forced_agents or {}).get(node_id) or node.get("forced_agent")
        if forced and attempt == 1 and forced in candidates:
            pool = [forced]
        else:
            pool = [c for c in candidates if c not in tried] or candidates
        chosen, why = route(pool)
        if forced and attempt == 1 and pool == [forced]:
            why = {**why, "reason": f"{forced} was chosen by the user (fork override)"}
        print(f"[ROUTING] node={node_id} skill={skill} chose={chosen} attempt={attempt}")
        await _emit(emit, "agent_routed", {"node_id": node_id, "skill": skill, "attempt": attempt, **why})
        manifest = get_manifest(chosen)
        call_started = time.time()
        try:
            state[node_id] = await _call_agent(skill, prompt, manifest)
            latency = round(time.time() - call_started, 2)
            quality, reason = assess(skill, state[node_id])
            stats = update_score(chosen, quality=quality, latency_s=latency)
            await _emit(emit, "reputation_updated", {"node_id": node_id, "agent": chosen, "skill": skill,
                                                     "quality": quality, "reason": reason,
                                                     "source": "output_check", "after": stats})
            meta[node_id] = {"status": "done", "agent": chosen, "attempts": attempt,
                             "duration_s": round(time.time() - started, 2), "error": None,
                             "quality": quality, "quality_reason": reason}
            await _emit(emit, "node_finished", {"node_id": node_id, "skill": skill,
                                                "output": state[node_id], **meta[node_id]})
            if skill == "fact_check":
                await _feedback_to_drafts(node, state[node_id], meta, emit)
            return
        except Exception as e:
            last_error = e
            tried.append(chosen)
            if is_infra_error(e):
                print(f"[INFRA ERROR] {chosen}: {e} (not counted against reputation)")
            else:
                stats = update_score(chosen, quality=0.0)
                await _emit(emit, "reputation_updated", {"node_id": node_id, "agent": chosen, "skill": skill,
                                                         "quality": 0.0, "reason": f"error: {str(e)[:120]}",
                                                         "source": "failure", "after": stats})
            if attempt < MAX_ATTEMPTS:
                await asyncio.sleep(BACKOFF_SECONDS * attempt)

    meta[node_id] = {"status": "failed", "agent": tried[-1], "attempts": len(tried),
                     "duration_s": round(time.time() - started, 2), "error": str(last_error)[:300]}
    await _emit(emit, "node_failed", {"node_id": node_id, "skill": skill, **meta[node_id]})


async def execute_plan(plan, query, emit=None, initial_state=None, forced_agents=None, instructions=None,
                       takeover=None):
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

        await asyncio.gather(*(run_node(n, state, query, meta, emit, forced_agents, instructions, takeover) for n in ready))
        remaining = [n for n in remaining if n["id"] not in meta]

    if any(n not in reused for n in state):
        skills = {n["id"]: n["agent"] for n in plan}
        agents = {nid: meta.get(nid, {}).get("agent") for nid in state}
        try:
            conflicts = await arbitrate(dict(state), skills, agents,
                                        emit=lambda t, p: _emit(emit, t, p))
        except Exception as e:
            print(f"[ARBITRATION ERROR] {type(e).__name__}: {e}")
            await _emit(emit, "arbitration_error", {"error": f"{type(e).__name__}: {str(e)[:200]}"})
        for c in conflicts:
            print(f"[CONFLICT] {c['explanation']}")
            await _emit(emit, "conflict_found", c)

    all_ok = all(m["status"] == "done" for m in meta.values())
    status = "complete" if all_ok else ("partial" if state else "failed")
    if status == "complete" and any(c["status"] == "open" for c in conflicts):
        status = "needs_review"  # human approval gate: open conflicts must be decided
    await _emit(emit, "run_finished", {"status": status})
    return {"outputs": state, "conflicts": conflicts, "node_status": meta, "status": status}