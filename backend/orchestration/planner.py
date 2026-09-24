import json
from agents.base_agent import run_agent

AVAILABLE_AGENTS = {
    "research": "Gathers facts on a topic",
    "drafting": "Writes prose based on research",
}

def plan_task(query: str) -> list:
    agent_list = "\n".join(f"- {k}: {v}" for k, v in AVAILABLE_AGENTS.items())
    prompt = f"""Task: "{query}"
Available agents:
{agent_list}
Return ONLY a JSON list of nodes, no other text, no markdown formatting.
Format: [{{"id": "n1", "agent": "research", "depends_on": []}}, {{"id": "n2", "agent": "drafting", "depends_on": ["n1"]}}]"""
    raw = run_agent("planner", prompt)
    raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(raw)