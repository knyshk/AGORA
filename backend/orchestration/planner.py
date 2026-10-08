import json
from agents.base_agent import run_agent

AVAILABLE_AGENTS = {
    "research": "Gathers facts on a topic",
    "drafting": "Writes prose based on research",
    "chart": "Describes a chart based on numeric data from research",
    "fact_check": "Verifies drafted claims against the original research",
}

async def plan_task(query: str) -> list:
    agent_list = "\n".join(f"- {k}: {v}" for k, v in AVAILABLE_AGENTS.items())
    prompt = f"""Task: "{query}"
Available agents:
{agent_list}

Rules:
- Use each agent at most once (maximum 4 nodes).
- Add a dependency ONLY if an agent truly needs another agent's output.
- "research" has no dependencies.
- "drafting" and "chart" must each depend ONLY on the research node, never on each other, so they can run in parallel.
- "fact_check" depends on the drafting node (and on the chart node if one exists).

Return ONLY a JSON list of nodes, no other text, no markdown formatting.
Format: [{{"id": "n1", "agent": "research", "depends_on": []}}, {{"id": "n2", "agent": "drafting", "depends_on": ["n1"]}}]"""
    raw = await run_agent("planner", prompt)
    raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(raw)