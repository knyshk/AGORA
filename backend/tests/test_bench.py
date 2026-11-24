import json
from collections import Counter
from unittest.mock import AsyncMock, patch

import pytest

from agents import chart_tools, factcheck_tools
from agents.grounding import context_numbers, is_grounded
from bench import grader, kappa, run_bench
from registry.registry import REGISTRY

TASKS = run_bench.load_tasks()


# ---------- the benchmark data itself ----------

def test_bench_has_five_tasks_per_skill_and_known_checks():
    assert Counter(t["skill"] for t in TASKS) == {"research": 5, "drafting": 5, "chart": 5, "fact_check": 5}
    assert len({t["id"] for t in TASKS}) == len(TASKS)
    for t in TASKS:
        assert set(t["checks"]) <= set(grader.CHECKS), t["id"]


@pytest.mark.parametrize("task", [t for t in TASKS if t["skill"] in ("drafting", "chart")], ids=lambda t: t["id"])
def test_expected_figures_really_are_in_the_frozen_context(task):
    nums = context_numbers(task["context"])
    for v in task["checks"].get("contains_numbers", []) + task["checks"].get("chart_points", []):
        assert is_grounded(float(v), nums), f"{task['id']}: {v} not in context"


@pytest.mark.parametrize("task", [t for t in TASKS if t["skill"] == "fact_check"], ids=lambda t: t["id"])
def test_fact_check_tasks_have_one_verdict_per_claim_and_frozen_sources(task):
    claims = factcheck_tools.extract_claims(task["context"])
    assert len(claims) == len(task["checks"]["verdicts"])
    cited_urls = {u for _, (_, u) in factcheck_tools.parse_sources(task["context"]).items()}
    assert cited_urls <= set(task["source_texts"])


# ---------- grader ----------

def test_gold_chart_scores_full_and_invented_point_is_penalised():
    data = {"title": "t", "chart_type": "bar", "x_label": "x", "y_label": "y",
            "data": [{"category": "Tesla", "value": 96.77}, {"category": "Ford", "value": 176.19},
                     {"category": "GM", "value": 171.84}]}
    gold = chart_tools.render_output(data, chart_tools.build_spec(data), [])
    task = next(t for t in TASKS if t["id"] == "C5")
    assert grader.grade_deterministic(task, gold)[0] == 1.0
    data["data"].append({"category": "Stellantis", "value": 189.5})
    bad = chart_tools.render_output(data, chart_tools.build_spec(data), [])
    score, details = grader.grade_deterministic(task, bad)
    assert score < 0.5 and "189.5" in details["chart_points"]["detail"]


def test_verdicts_parsed_from_real_fact_check_table():
    claims = [{"id": 1, "text": "a [1]", "sources": [1]}, {"id": 2, "text": "b [1]", "sources": [1]}]
    results = {1: {"verdict": "supported", "quote": "q", "note": ""},
               2: {"verdict": "contradicted", "quote": "", "note": "x"}}
    out = factcheck_tools.render(claims, results, {1: ("t", "u")})
    assert grader.parse_verdicts(out) == ["supported", "contradicted"]
    assert grader.check_verdicts(out, ["supported", "unsupported"])[0] == 0.5
    results[2]["verdict"] = "unsupported"
    out = factcheck_tools.render(claims, results, {1: ("t", "u")})
    assert grader.parse_verdicts(out) == ["supported", "unsupported"]  # "supported" is inside "unsupported"


def test_text_checks():
    out = "Tesla made $96.77 billion [1] and Ford $176,191 million [2].\n\n---\nSources\n[1] a - u\n[2] b - v"
    assert grader.check_contains_numbers(out, [96.77, 176.19])[0] == 1.0
    assert grader.check_min_citations(out, 3)[0] == pytest.approx(2 / 3)
    assert grader.check_has_sources(out, True)[0] == 1.0
    assert grader.check_max_words(out, 5)[0] < 1.0


def test_judge_uses_a_different_provider_and_combines():
    assert grader.judge_provider("groq") != "groq"
    assert grader.judge_provider("gemini") != "gemini"
    assert grader.parse_judge('noise {"score": 4, "reason": "ok"}') == (4, "ok")
    assert grader.combine(1.0, {"score": 0.5}) == 0.85
    assert grader.combine(0.8, None) == 0.8


# ---------- runner, priors, kappa ----------

async def test_run_one_scores_and_excludes_infra_errors():
    task = next(t for t in TASKS if t["id"] == "C1")
    data = {"title": "t", "chart_type": "bar", "x_label": "x", "y_label": "y",
            "data": [{"category": "2022", "value": 81.46}, {"category": "2023", "value": 96.77}]}
    gold = chart_tools.render_output(data, chart_tools.build_spec(data), [])
    manifest = REGISTRY["chart-v1"]
    with patch.object(run_bench, "_call_agent", new=AsyncMock(return_value=gold)):
        rec = await run_bench.run_one(task, manifest, use_judge=False)
    assert rec["score"] == 1.0 and rec["error"] is None
    with patch.object(run_bench, "_call_agent", new=AsyncMock(side_effect=RuntimeError("429 rate limit"))):
        rec = await run_bench.run_one(task, manifest, use_judge=False)
    assert rec["infra_error"] and rec["score"] is None
    with patch.object(run_bench, "_call_agent", new=AsyncMock(side_effect=ValueError("bad output"))):
        rec = await run_bench.run_one(task, manifest, use_judge=False)
    assert not rec["infra_error"] and rec["score"] == 0.0


async def test_fact_check_bench_uses_frozen_sources_not_the_network():
    task = next(t for t in TASKS if t["id"] == "F1")
    seen = []

    async def fake_agent(skill, prompt, manifest):
        for c in factcheck_tools.extract_claims(prompt):
            seen.append(await factcheck_tools.fetch_source_text(
                factcheck_tools.parse_sources(prompt)[c["sources"][0]][1]))
        return ""
    with patch.object(run_bench, "_call_agent", new=fake_agent):
        await run_bench.run_one(task, REGISTRY["fact_check-v1"], use_judge=False)
    assert all("Official annual revenue" in s for s in seen) and len(seen) == 2


def test_summary_and_priors():
    recs = [{"agent": "a", "skill": "chart", "model": "m", "strategy": "spec", "score": s,
             "infra_error": False, "latency_s": 1.0} for s in (1.0, 0.5, 1.0)]
    recs.append({"agent": "a", "skill": "chart", "model": "m", "strategy": "spec", "score": None,
                 "infra_error": True, "latency_s": 9.0})
    s = run_bench.summarise(recs)["a"]
    assert s["n_scored"] == 3 and s["n_infra_errors"] == 1 and s["mean"] == pytest.approx(0.833, abs=1e-3)
    assert run_bench.derive_priors(recs)["a"]["prior"] == pytest.approx((2.5 + 1) / 5, abs=1e-3)
    assert "| a | chart |" in run_bench.summary_markdown(run_bench.summarise(recs),
                                                         {"finished_at": "x", "n_tasks": 1, "judge": False})


def test_cohens_kappa():
    assert kappa.cohens_kappa([1, 1, 0, 0], [1, 1, 0, 0]) == 1.0
    assert kappa.cohens_kappa([1, 0, 1, 0], [0, 1, 0, 1]) == -1.0
    assert kappa.cohens_kappa([1, 1, 1, 0], [1, 1, 0, 0]) == pytest.approx(0.5)


def test_kappa_export_and_score(tmp_path):
    results = tmp_path / "bench_X.json"
    results.write_text(json.dumps({"records": [
        {"task": "D1", "agent": "a", "judge": {"score": 1.0}, "output": "x"},
        {"task": "D2", "agent": "a", "judge": {"score": 0.25}, "output": "y"},
        {"task": "D3", "agent": "a", "judge": None, "output": "z"}]}))
    csv_path = kappa.export(str(results))
    text = csv_path.read_text().splitlines()
    assert len(text) == 3
    csv_path.write_text("\n".join([text[0], text[1].replace(",1,,", ",1,1,"), text[2].replace(",0,,", ",0,0,")]))
    assert kappa.score(str(csv_path)) == {"n": 2, "agreement": 1.0, "kappa": 1.0}
