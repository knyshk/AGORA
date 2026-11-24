import asyncio
import os
import time
from agents.base_agent import _only_provider, force_provider, run_agent
from config import LOCAL_PROVIDERS
from registry.registry import REGISTRY, get_agents_for_skill, get_manifest
from security import audit, task_tokens
from security.task_tokens import TaskTokenError
from reputation.scoring import route, update_score
from reputation.quality import assess, draft_feedback
from arbitration.structured import arbitrate
from agents.research_tools import grounded_research
from agents.chart_tools import build_chart, strip_chart_blocks
from agents.drafting_tools import write_draft
from agents.factcheck_tools import fact_check
from agents.usage import start_ledger, summarise
from orchestration.budget import Budget, default_budget
from orchestration.self_correct import self_correct

MAX_ATTEMPTS = 2
BACKOFF_SECONDS = 2
NODE_TIMEOUT_S = float(os.getenv("NODE_TIMEOUT_S", "90"))  # per agent call; a timeout reassigns the node


def is_infra_error(e: Exception) -> bool:
    """Rate limits, timeouts, and connection errors are not the agent's fault."""
    name = type(e).__name__.lower()
    msg = str(e).lower()
    infra_signals = ["ratelimit", "timeout", "timed out", "connection", "429", "503", "502", "providers exhausted"]
    return any(s in name or s in msg for s in infra_signals)

async def _dispatch(skill, prompt, manifest):
    """Run the agent's strategy. Only reached through invoke_agent (token-checked)."""
    if skill == "research" and getattr(manifest, "strategy", "plain") == "grounded":
        return await grounded_research(prompt, provider=manifest.provider, model=manifest.model)
    if skill == "drafting" and getattr(manifest, "strategy", "plain") == "cited":
        return await write_draft(prompt, provider=manifest.provider, model=manifest.model)
    if skill == "fact_check" and getattr(manifest, "strategy", "plain") == "verify":
        return await fact_check(prompt, provider=manifest.provider, model=manifest.model)
    if skill == "chart" and getattr(manifest, "strategy", "plain") == "spec":
        return await build_chart(prompt, provider=manifest.provider, model=manifest.model)
    return await run_agent(skill, prompt, provider=manifest.provider, model=manifest.model)


async def invoke_agent(agent_name: str, prompt: str, task_token: str) -> str:
    """The agent gateway, used by direct calls and by the MCP server: the agent must have a verified
    signed manifest, and the task token must be valid for exactly this agent and skill."""
    manifest = REGISTRY.get(agent_name)
    if manifest is None or not manifest.verified:
        raise TaskTokenError(f"agent '{agent_name}' has no verified signed manifest")
    try:
        claims = task_tokens.check(task_token, agent_name, manifest.skill)
    except TaskTokenError as e:
        audit.record("gateway", "agent_call_refused", agent_name, {"reason": str(e)})
        raise
    audit.record(f"agent:{agent_name}", "agent_invoked", f"{claims['run']}/{claims['node']}",
                 {"skill": manifest.skill, "model": manifest.model, "token_id": claims["jti"]})
    return await _dispatch(manifest.skill, prompt, manifest)


async def _call_agent(skill, prompt, manifest, run_id="adhoc", node_id="-"):
    token = task_tokens.issue(run_id, node_id, manifest.name, skill)
    if os.getenv("AGENT_TRANSPORT", "direct") == "mcp":
        from agents.mcp_client import call_agent_over_mcp
        return await call_agent_over_mcp(manifest.name, prompt, token)
    return await invoke_agent(manifest.name, prompt, token)

async def _emit(emit, event_type, payload):
    if emit is None:
        return
    try:
        await emit(event_type, payload)
    except Exception as e:
        print(f"[EMIT ERROR] {event_type}: {e}")


async def _spend(budget, cost, emit):
    changed = budget.add(cost)
    if changed:
        await _emit(emit, f"budget_{changed}", budget.snapshot())


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


async def run_node(node, state, query, meta, emit=None, forced_agents=None, instructions=None, takeover=None,
                   budget=None):
    node_id = node["id"]
    skill = node["agent"]
    started = time.time()
    budget = budget or Budget()
    if budget.exhausted:
        meta[node_id] = {"status": "skipped", "agent": None, "attempts": 0, "duration_s": 0,
                         "error": f"Skipped: run budget of ${budget.limit} (notional) is used up"}
        await _emit(emit, "node_skipped", {"node_id": node_id, "skill": skill, "depends_on": node["depends_on"],
                                           **meta[node_id]})
        return
    await _emit(emit, "node_started", {"node_id": node_id, "skill": skill, "depends_on": node["depends_on"]})
    if await _human_node(node, state, meta, emit, takeover, started):
        return
    if takeover:
        takeover.mark_started(node_id)

    candidates = get_agents_for_skill(skill)
    if _only_provider.get():   # local LLM mode: only agents that run on the local model
        candidates = [c for c in candidates if REGISTRY[c].provider == _only_provider.get()]
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

    ledger = start_ledger()  # every LLM call this node makes, including retries and fallbacks
    tried = []
    last_error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        forced = (forced_agents or {}).get(node_id) or node.get("forced_agent")
        if forced and attempt == 1 and forced in candidates:
            pool = [forced]
        else:
            pool = [c for c in candidates if c not in tried] or candidates
            economy = budget.filter_pool(pool, REGISTRY)
            if economy != pool:
                await _emit(emit, "budget_downgrade", {"node_id": node_id, "skill": skill, "from": pool,
                                                       "to": economy, **budget.snapshot()})
                pool = economy
        chosen, why = route(pool)
        if forced and attempt == 1 and pool == [forced]:
            why = {**why, "reason": f"{forced} was chosen by the user (fork override)"}
        print(f"[ROUTING] node={node_id} skill={skill} chose={chosen} attempt={attempt}")
        await _emit(emit, "agent_routed", {"node_id": node_id, "skill": skill, "attempt": attempt, **why})
        manifest = get_manifest(chosen)
        call_started = time.time()
        try:
            limit = NODE_TIMEOUT_S * (3 if manifest.provider in LOCAL_PROVIDERS else 1)
            state[node_id] = await asyncio.wait_for(
                _call_agent(skill, prompt, manifest, getattr(emit, "run_id", "adhoc"), node_id), limit)
            latency = round(time.time() - call_started, 2)
            quality, reason = assess(skill, state[node_id])
            stats = update_score(chosen, quality=quality, latency_s=latency)
            await _emit(emit, "reputation_updated", {"node_id": node_id, "agent": chosen, "skill": skill,
                                                     "quality": quality, "reason": reason,
                                                     "source": "output_check", "after": stats})
            meta[node_id] = {"status": "done", "agent": chosen, "attempts": attempt,
                             "duration_s": round(time.time() - started, 2), "error": None,
                             "quality": quality, "quality_reason": reason, "usage": summarise(ledger)}
            await _spend(budget, meta[node_id]["usage"]["cost_usd"], emit)
            await _emit(emit, "node_finished", {"node_id": node_id, "skill": skill,
                                                "output": state[node_id], **meta[node_id]})
            if skill == "fact_check":
                await _feedback_to_drafts(node, state[node_id], meta, emit)
            return
        except Exception as e:
            if isinstance(e, asyncio.TimeoutError):
                e = TimeoutError(f"agent call timed out after {NODE_TIMEOUT_S:.0f}s")
            last_error = e
            tried.append(chosen)
            await _emit(emit, "node_attempt_failed", {"node_id": node_id, "agent": chosen, "attempt": attempt,
                                                      "error": str(e)[:200], "infra": is_infra_error(e)})
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
                     "duration_s": round(time.time() - started, 2), "error": str(last_error)[:300],
                     "usage": summarise(ledger)}
    await _spend(budget, meta[node_id]["usage"]["cost_usd"], emit)
    await _emit(emit, "node_failed", {"node_id": node_id, "skill": skill, **meta[node_id]})


async def execute_plan(plan, query, emit=None, initial_state=None, forced_agents=None, instructions=None,
                       takeover=None, budget_usd=None, local_only=False, sequential=False):
    if local_only:
        force_provider("ollama")   # every LLM call of this run, including arbitration, stays on the laptop
    budget = Budget(budget_usd if budget_usd is not None else default_budget())
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

        if sequential:   # evaluation baseline: one node at a time, same order
            for n in ready:
                await run_node(n, state, query, meta, emit, forced_agents, instructions, takeover, budget)
        else:
            await asyncio.gather(*(run_node(n, state, query, meta, emit, forced_agents, instructions, takeover, budget)
                                   for n in ready))
        remaining = [n for n in remaining if n["id"] not in meta]

    correction_ledger = start_ledger()
    corrections = []
    if not budget.exhausted:
        corrections = await self_correct(plan, query, state, meta, lambda t, p: _emit(emit, t, p),
                                         _call_agent, get_manifest, getattr(emit, "run_id", "adhoc"))
    correction_usage = summarise(correction_ledger)
    await _spend(budget, correction_usage["cost_usd"], emit)

    arbitration_ledger = start_ledger()
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
    usage = run_usage(meta, summarise(arbitration_ledger), budget, correction_usage)
    await _emit(emit, "run_finished", {"status": status, "usage": usage})
    return {"outputs": state, "conflicts": conflicts, "node_status": meta, "status": status, "usage": usage,
            "self_correction": corrections}


def run_usage(meta: dict, arbitration: dict, budget, self_correction: dict | None = None) -> dict:
    nodes = {nid: m["usage"] for nid, m in meta.items() if m.get("usage")}
    self_correction = self_correction or {"llm_calls": 0, "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0,
                                          "tokens_estimated": False}
    parts = list(nodes.values()) + [arbitration, self_correction]
    return {"nodes": nodes, "arbitration": arbitration, "self_correction": self_correction,
            "total": {"llm_calls": sum(p["llm_calls"] for p in parts),
                      "tokens_in": sum(p["tokens_in"] for p in parts),
                      "tokens_out": sum(p["tokens_out"] for p in parts),
                      "cost_usd": round(sum(p["cost_usd"] for p in parts), 6),
                      "tokens_estimated": any(p["tokens_estimated"] for p in parts)},
            "budget": budget.snapshot(), "pricing": "notional (free tiers are actually $0)"}