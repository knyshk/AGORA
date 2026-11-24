"""AGORA-Bench grading: deterministic checks first, an LLM judge only for open-ended quality.

Every check returns a score in [0, 1]; the deterministic score is their mean.
The judge (when the task has a rubric) uses a DIFFERENT provider from the agent being graded,
so a model never grades itself. final = 0.7 * deterministic + 0.3 * judge.
"""
import json
import re

from agents.base_agent import _make_llm
from agents.drafting_tools import cited_ids
from agents.grounding import context_numbers, is_grounded
from config import FALLBACK_CHAIN

DETERMINISTIC_WEIGHT = 0.7
VERDICT_WORDS = ("unsupported", "contradicted", "unverifiable", "supported")  # "supported" last: it is inside "unsupported"

JUDGE_PROMPT = """You are grading an AI agent's output for a benchmark. Be strict and consistent.
Task given to the agent: {task}
{context}
Grading question: {rubric}

Agent output:
<<<
{output}
>>>

Score 1-5: 5 = fully meets the grading question with no errors, 3 = partly, 1 = fails or contains invented facts.
Return ONLY JSON: {{"score": 1, "reason": "one sentence"}}"""


def _body(output: str) -> str:
    return output.split("\n---\n", 1)[0]


def check_contains_numbers(output, expected):
    nums = context_numbers(output)
    hits = [v for v in expected if is_grounded(float(v), nums)]
    return len(hits) / len(expected), f"{len(hits)}/{len(expected)} expected figures present"


def check_min_citations(output, n):
    got = len(set(cited_ids(_body(output))))
    return min(1.0, got / n), f"{got} distinct citation(s), need {n}"


def check_has_sources(output, _):
    ok = "\nSources\n" in output
    return float(ok), "source list present" if ok else "no source list"


def check_citation_check_passed(output, _):
    ok = "Citation check: passed" in output
    return float(ok), "citation check passed" if ok else "citation check not passed"


def check_max_words(output, n):
    words = len(_body(output).split())
    return (1.0 if words <= n else max(0.0, 1 - (words - n) / n)), f"{words} words (limit {n})"


def check_mentions(output, items):
    hits = [x for x in items if x in output]
    return len(hits) / len(items), f"mentions {len(hits)}/{len(items)}: {items}"


def chart_values(output):
    m = re.search(r"```vega-lite\s*(.*?)```", output, flags=re.S)
    if not m:
        return None
    try:
        return [float(v["value"]) for v in json.loads(m.group(1))["data"]["values"]]
    except (ValueError, KeyError, TypeError):
        return None


def check_chart_points(output, expected):
    values = chart_values(output)
    if values is None:
        return 0.0, "no chart spec"
    recall = sum(1 for e in expected if is_grounded(float(e), values)) / len(expected)
    extra = [v for v in values if not any(is_grounded(v, [float(e)]) for e in expected)]
    precision = (len(values) - len(extra)) / len(values) if values else 0.0
    return recall * precision, f"recall {recall:.2f}, precision {precision:.2f}, extra points {extra}"


def check_chart_max_points(output, n):
    values = chart_values(output) or []
    return float(0 < len(values) <= n), f"{len(values)} point(s), max {n}"


def parse_verdicts(output):
    verdicts = {}
    for line in output.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 3 and cells[0].isdigit():
            word = next((w for w in VERDICT_WORDS if w in cells[2]), None)
            if word:
                verdicts[int(cells[0])] = word
    return [verdicts.get(i) for i in range(1, max(verdicts, default=0) + 1)]


def check_verdicts(output, expected):
    got = parse_verdicts(output)
    right = sum(1 for i, e in enumerate(expected) if i < len(got) and got[i] == e)
    return right / len(expected), f"verdicts {got} vs expected {expected}"


CHECKS = {
    "contains_numbers": check_contains_numbers, "min_citations": check_min_citations,
    "has_sources": check_has_sources, "citation_check_passed": check_citation_check_passed,
    "max_words": check_max_words, "mentions": check_mentions, "chart_points": check_chart_points,
    "chart_max_points": check_chart_max_points, "verdicts": check_verdicts,
}


def grade_deterministic(task: dict, output: str) -> tuple:
    details = {}
    for name, arg in task.get("checks", {}).items():
        score, why = CHECKS[name](output or "", arg)
        details[name] = {"score": round(score, 3), "detail": why}
    scores = [d["score"] for d in details.values()]
    return (round(sum(scores) / len(scores), 3) if scores else None), details


def judge_provider(agent_provider: str):
    """First provider in the fallback chain that is not the graded agent's provider."""
    return next((p for p in FALLBACK_CHAIN if p != agent_provider), None)


def parse_judge(raw: str):
    m = re.search(r"\{.*\}", raw, flags=re.S)
    data = json.loads(m.group(0))
    score = int(data["score"])
    if not 1 <= score <= 5:
        raise ValueError("judge score out of range")
    return score, str(data.get("reason", ""))[:300]


async def judge(task: dict, output: str, agent_provider: str) -> dict | None:
    if not task.get("rubric") or not output:
        return None
    provider = judge_provider(agent_provider)
    if provider is None:
        return None
    context = f"Research context the agent was given:\n{task['context'][:3000]}\n" if task.get("context") else ""
    prompt = JUDGE_PROMPT.format(task=task["task"], context=context, rubric=task["rubric"], output=output[:6000])
    try:
        raw = (await _make_llm(provider, timeout=40).ainvoke(prompt)).content
        score, reason = parse_judge(raw)
    except Exception as e:
        print(f"[JUDGE] {provider} failed: {type(e).__name__}: {str(e)[:120]}")
        return None
    return {"provider": provider, "score_1_5": score, "score": round((score - 1) / 4, 3), "reason": reason}


def combine(deterministic: float | None, judged: dict | None) -> float:
    if deterministic is None and judged is None:
        return 0.0
    if judged is None:
        return deterministic
    if deterministic is None:
        return judged["score"]
    return round(DETERMINISTIC_WEIGHT * deterministic + (1 - DETERMINISTIC_WEIGHT) * judged["score"], 3)
