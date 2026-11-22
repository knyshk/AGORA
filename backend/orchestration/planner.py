import json
from agents.base_agent import run_agent
from orchestration.validation import validate_plan, PlanError

AVAILABLE_AGENTS = {
    "research": "Gathers facts on a topic",
    "drafting": "Writes prose based on research",
    "chart": "Describes a chart based on numeric data from research",
    "fact_check": "Verifies drafted claims against the original research",
}

MAX_ATTEMPTS = 2

RULES = """Rules:
- Use each agent at most once (maximum 4 nodes).
- Add a dependency ONLY if an agent truly needs another agent's output.
- "research" has no dependencies.
- "drafting" and "chart" must each depend ONLY on the research node, never on each other, so they can run in parallel.
- "fact_check" depends on the drafting node (and on the chart node if one exists).

Return ONLY a JSON list of nodes, no other text, no markdown formatting."""

FORMAT = 'Format: [{"id": "n1", "agent": "research", "depends_on": []}, {"id": "n2", "agent": "drafting", "depends_on": ["n1"]}]'


def _build_prompt(query: str, error: str = None) -> str:
    agent_list = "\n".join(f"- {k}: {v}" for k, v in AVAILABLE_AGENTS.items())
    prompt = f'Task: "{query}"\nAvailable agents:\n{agent_list}\n\n{RULES}\n{FORMAT}'
    if error:
        prompt += f"\n\nYour previous answer was rejected: {error}. Fix it and return only valid JSON."
    return prompt


def _parse(raw: str):
    raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(raw)


async def plan_task(query: str) -> list:
    last_error = None
    for _ in range(MAX_ATTEMPTS):
        raw = await run_agent("planner", _build_prompt(query, last_error))
        try:
            return validate_plan(_parse(raw), AVAILABLE_AGENTS)
        except (json.JSONDecodeError, PlanError) as e:
            last_error = str(e)
    raise PlanError(f"Planner failed after {MAX_ATTEMPTS} attempts: {last_error}")