import asyncio
from agents.base_agent import run_agent
from mcp.registry import get_agents_for_skill, get_manifest
from reputation.scoring import pick_best_agent, update_score

async def run_node(node, state, query):
    candidates = get_agents_for_skill(node["agent"])
    if not candidates:
        raise RuntimeError(f"No registered agent for skill '{node['agent']}'")
    chosen = pick_best_agent(candidates)
    skill = node["agent"]
    print(f"[ROUTING] skill={skill} chose={chosen}")
    manifest = get_manifest(chosen)
    context = "\n".join(f"{d}: {state[d]}" for d in node["depends_on"])
    prompt = f"Task: {query}\nContext from previous agents:\n{context}" if context else f"Task: {query}"
    try:
        state[node["id"]] = run_agent(node["agent"], prompt, provider=manifest.provider, model=manifest.model)
        update_score(chosen, success=True)
    except Exception as e:
        update_score(chosen, success=False)
        raise

async def execute_plan(plan, query):
    state = {}
    remaining = plan.copy()
    while remaining:
        ready = [n for n in remaining if all(d in state for d in n["depends_on"])]
        if not ready:
            raise RuntimeError(f"Deadlock: remaining nodes have unmet dependencies: {remaining}")
        await asyncio.gather(*(run_node(n, state, query) for n in ready))
        remaining = [n for n in remaining if n["id"] not in state]
    return state
