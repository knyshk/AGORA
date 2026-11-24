from unittest.mock import AsyncMock, patch

from agents import factcheck_tools
from orchestration import executor, self_correct

PLAN = [{"id": "n1", "agent": "research", "depends_on": []},
        {"id": "n2", "agent": "drafting", "depends_on": ["n1"]},
        {"id": "n3", "agent": "fact_check", "depends_on": ["n2"]}]


def fc_output(results):
    claims = [{"id": i, "text": f"claim {i} [1]", "sources": [1]} for i in range(1, len(results) + 1)]
    res = {i: {"verdict": v, "quote": "q", "note": ""} for i, v in enumerate(results, 1)}
    return factcheck_tools.render(claims, res, {1: ("t", "u")})


BAD = fc_output(["supported", "unsupported", "contradicted", "supported"])
GOOD = fc_output(["supported", "supported", "supported"])
WORSE = fc_output(["contradicted", "contradicted", "supported"])


def test_flagged_claims_and_rate():
    flagged = self_correct.flagged_claims(BAD)
    assert [(f["id"], f["verdict"]) for f in flagged] == [(2, "unsupported"), (3, "contradicted")]
    assert self_correct.supported_rate(BAD) == 0.5 and self_correct.supported_rate(GOOD) == 1.0
    assert self_correct.flagged_claims(GOOD) == []


async def _run(fact_checks, drafts):
    events = []

    async def emit(t, p):
        events.append((t, p))

    fc_iter, draft_iter = iter(fact_checks), iter(drafts)

    async def dispatch(skill, prompt, manifest):
        if skill == "fact_check":
            return next(fc_iter)
        if skill == "drafting":
            if "A fact-checker checked your previous draft" in prompt:
                assert "[contradicted] claim 3" in prompt     # the evidence is fed back
            return next(draft_iter)
        return "research [1]\n\n---\nSources\n[1] t - u"

    with patch.object(executor, "_dispatch", new=dispatch), \
         patch.object(executor, "update_score", return_value={"mean": 0.7}), \
         patch.object(executor, "route", side_effect=lambda c: (c[0], {"reason": "first"})), \
         patch.object(executor, "arbitrate", new=AsyncMock(return_value=[])):
        result = await executor.execute_plan(PLAN, "q", emit=emit)
    return result, events


async def test_revision_is_accepted_when_more_claims_are_supported():
    result, events = await _run([BAD, GOOD], ["draft v1", "draft v2"])
    assert result["outputs"]["n2"] == "draft v2" and result["outputs"]["n3"] == GOOD
    rev = result["node_status"]["n2"]["revision"]
    assert rev["supported_rate_before"] == 0.5 and rev["supported_rate_after"] == 1.0
    assert rev["original_output"] == "draft v1" and rev["rounds"] == 1
    assert result["self_correction"][0]["revised"] is True
    kinds = [t for t, _ in events]
    assert kinds.count("node_revised") == 2 and "self_correction_finished" in kinds


async def test_revision_that_makes_things_worse_is_rejected():
    result, events = await _run([BAD, WORSE], ["draft v1", "draft v2"])
    assert result["outputs"]["n2"] == "draft v1" and result["outputs"]["n3"] == BAD
    finished = next(p for t, p in events if t == "self_correction_finished")
    assert finished["accepted"] is False and "revision" not in result["node_status"]["n2"]


async def test_nothing_flagged_means_no_extra_calls():
    result, events = await _run([GOOD], ["draft v1"])
    assert not any(t.startswith("self_correction") for t, _ in events)
    assert result["self_correction"][0]["revised"] is False
