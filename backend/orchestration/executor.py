import asyncio
from agents.base_agent import run_agent
from registry.registry import get_agents_for_skill, get_manifest
from reputation.scoring import pick_best_agent, update_score
from arbitration.engine import detect_conflict


def is_infra_error(e: Exception) -> bool:
    """Rate limits, timeouts, and connection errors are not the agent's fault."""
    name = type(e).__name__.lower()
    msg = str(e).lower()
    infra_signals = ["ratelimit", "timeout", "connection", "429", "503", "502"]
    return any(s in name or s in msg for s in infra_signals)


async def run_node(node, state, query):
    candidates = get_agents_for_skill(node["agent"])
    if not candidates:
        raise RuntimeError(f"No registered agent for skill '{node['agent']}'")
    chosen = pick_best_agent(candidates)
    print(f"[ROUTING] skill={node['agent']} chose={chosen}")
    manifest = get_manifest(chosen)
    context = "\n".join(f"{d}: {state[d]}" for d in node["depends_on"])
    prompt = node.get("forced_prompt") or (
        f"Task: {query}\nContext from previous agents:\n{context}" if context else f"Task: {query}"
    )
    try:
        state[node["id"]] = await run_agent(node["agent"], prompt, provider=manifest.provider, model=manifest.model)
        update_score(chosen, success=True)
    except Exception as e:
        if is_infra_error(e):
            print(f"[INFRA ERROR] {chosen}: {e} (not counted against reputation)")
        else:
            update_score(chosen, success=False)
        raise


async def execute_plan(plan, query):
    state = {}
    conflicts = []
    remaining = plan.copy()
    while remaining:
        ready = [n for n in remaining if all(d in state for d in n["depends_on"])]
        if not ready:
            raise RuntimeError(f"Deadlock: {remaining}")
        await asyncio.gather(*(run_node(n, state, query) for n in ready))
        remaining = [n for n in remaining if n["id"] not in state]

    ids = list(state.keys())
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            a, b = ids[i], ids[j]
            conflict = await detect_conflict(state[a], state[b], label_a=a, label_b=b)
            if conflict:
                conflicts.append({"between": [a, b], **conflict})
                print(f"[CONFLICT] {a} vs {b}: {conflict['explanation']}")

    return {"outputs": state, "conflicts": conflicts}