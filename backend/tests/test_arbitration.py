import json
import time
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from agents import chart_tools
from arbitration import claims as cl
from arbitration import resolution, structured
from db import crud
from db.database import init_db
from db.recorder import RunRecorder

SEC = {"id": 1, "title": "SEC EDGAR 10-K data: Tesla", "url": "https://data.sec.gov/api/xbrl/x.json"}


def claim(node, value, scale="billion", entity="Tesla", attribute="revenue", period="2023", unit="USD",
          sources=None, agent="a"):
    return cl.make_claim(node, agent, entity, attribute, period, value, scale, unit, "q", sources or [])


@pytest.fixture(autouse=True)
def no_redis():
    with patch.object(structured, "get_stats", return_value={"mean": 0.8}):
        yield


# ---------- normalisation ----------

def test_normalisation():
    assert cl.normalize_entity("Tesla, Inc.") == "tesla"
    assert cl.normalize_entity("General Motors Co") == "gm"
    assert cl.normalize_entity("Ford Motor Company") == "ford"
    assert cl.normalize_attribute("Total Net Sales") == "revenue"
    assert cl.normalize_attribute("Net profit") == "net income"
    assert cl.normalize_period("fiscal 2023") == "2023" and cl.normalize_period("FY2024") == "2024"
    assert cl.unit_kind("USD") == "currency" and cl.unit_kind("%") == "percent" and cl.unit_kind("m") == "length"


# ---------- comparison: true conflicts and hard negatives ----------

@pytest.mark.parametrize("a,b,same", [
    (claim("x", 96.77), claim("y", 97.69), False),                       # digits swapped
    (claim("x", 96.77), claim("y", 97, ), True),                         # "about $97 billion" is a rounding
    (claim("x", 96.77), claim("y", 97.0), True),                         # ...even when the model returns 97.0
    (claim("x", 211.92), claim("y", 212.0), True),
    (claim("x", 96.77), claim("y", 96.8), True),                         # rounding to one decimal
    (claim("x", 176.19), claim("y", 176191, scale="million"), True),     # same value, other unit
    (claim("x", 383.29), claim("y", 383.29, scale="million"), False),    # million vs billion
    (claim("x", 171.84), claim("y", 171840000000), True),                # model expanded the number and kept "billion"
    (claim("x", 383.29), claim("y", 338290000000), False),               # ...and a real digit swap is still caught
    (claim("x", 8848.86, scale="", unit="m"), claim("y", 8849, scale="", unit="m"), True),
    (claim("x", 8848.86, scale="", unit="m"), claim("y", 8848, scale="", unit="m"), False),
])
def test_agree(a, b, same):
    assert structured.agree(a, b) is same


def test_conflict_found_with_source_authority_policy():
    claims = [claim("n1", 96.77, sources=[SEC], agent="research-v1"),
              claim("n2", 97.69, agent="research-v2"), claim("n3", 97.69, agent="drafting-v1")]
    conflicts = structured.find_conflicts(claims, {"n1": "research", "n2": "research", "n3": "drafting"})
    assert len(conflicts) == 1
    c = conflicts[0]
    assert c["between"] == ["n1", "n2", "n3"] and c["status"] == "auto_resolved"   # official vs uncited: low-stakes
    assert c["resolution"]["by"] == "policy" and c["resolution"]["value"] == "$96.77 billion"
    assert c["policy"] == "source authority"
    assert c["sides"][0]["nodes"] == ["n1"] and c["sides"][0]["value"] == "$96.77 billion"
    assert c["sides"][1]["nodes"] == ["n2", "n3"]
    assert "SEC" in c["suggested_resolution"]


def test_no_conflict_for_different_periods_entities_metrics_or_same_node():
    claims = [claim("n1", 96.77), claim("n2", 81.46, period="2022"), claim("n2", 176.19, entity="Ford"),
              claim("n2", 15.0, attribute="net income"), claim("n3", 1.0, entity="Acme"), claim("n3", 2.0, entity="Acme")]
    assert structured.find_conflicts(claims, {}) == []


def test_trust_vote_when_authority_is_similar():
    claims = [claim("n1", 96.77, agent="a"), claim("n2", 97.69, agent="b")]
    with patch.object(structured, "get_stats", side_effect=lambda a: {"mean": 0.9 if a == "b" else 0.5}):
        c = structured.find_conflicts(claims, {"n1": "research", "n2": "research"})[0]
    assert c["policy"] == "trust-weighted vote" and c["sides"][0]["nodes"] == ["n2"]


# ---------- extraction ----------

def test_chart_claims_read_from_spec():
    data = {"title": "t", "chart_type": "grouped_bar", "x_label": "Company", "y_label": "Revenue",
            "unit": "USD billions", "data": [{"category": "Tesla", "series": "2023", "value": 96.77}]}
    out = chart_tools.render_output(data, chart_tools.build_spec(data), [])
    (c,) = cl.chart_claims("n3", "chart-v1", out)
    assert (c["entity"], c["attribute"], c["period"], c["absolute"]) == ("tesla", "revenue", "2023", 96.77e9)


async def test_text_claims_attach_cited_sources():
    text = ("Tesla's revenue was $96.77 billion in 2023 [1].\n\n---\nSources\n"
            "[1] SEC EDGAR 10-K data: Tesla - https://data.sec.gov/api/xbrl/x.json\n[2] Blog - https://b.com")
    reply = json.dumps([{"entity": "Tesla", "attribute": "total revenue", "period": "2023", "value": 96.77,
                         "scale": "billion", "unit": "USD", "quote": "Tesla's revenue was $96.77 billion in 2023 [1]."}])
    with patch.object(cl, "run_agent", new=AsyncMock(return_value=reply)) as llm:
        (c,) = await cl.extract_claims("n1", "research", "research-v1", text)
    assert "Sources" not in llm.await_args.args[1]
    assert c["attribute"] == "revenue" and c["sources"][0]["url"].startswith("https://data.sec.gov")


async def test_fact_check_and_empty_nodes_cost_no_llm_call():
    with patch.object(cl, "run_agent", new=AsyncMock()) as llm:
        assert await cl.extract_claims("n4", "fact_check", "f", "Tesla $96.77 billion [1]") == []
        assert await cl.extract_claims("n2", "drafting", "d", "   ") == []
    assert llm.await_count == 0


def test_counts_share_one_unit_and_changes_are_signed():
    a = claim("x", 140473, scale="", attribute="number of employees", unit="people")
    b = claim("y", 127855, scale="", attribute="employees", unit="employees")
    assert structured.group_key(a) == structured.group_key(b)
    fell = claim("x", -2.8, scale="", attribute="net sales change", unit="%")
    rose = claim("y", 2.8, scale="", attribute="net sales change", unit="%")
    assert len(structured.find_conflicts([fell, rose], {})) == 1


def text_claim(node, value, entity="Australia", attribute="capital", quote=None):
    return cl.make_text_claim(node, "a", entity, attribute, "", value, quote or f"The {attribute} is {value}.", [])


async def test_text_conflicts_are_confirmed_by_entailment_only_inside_a_group():
    claims = [text_claim("a", "Canberra"), text_claim("b", "Sydney"),
              text_claim("a", "Elon Musk", "Tesla", "chief executive"),
              text_claim("b", "Elon Musk", "Tesla", "chief executive"),          # same value: no check
              text_claim("a", "Canberra", "Australia", "seat of government"),
              text_claim("b", "Canberra, ACT", "Australia", "seat of government")]
    assert structured.find_conflicts(claims, {}) == []                           # numeric pass ignores text
    replies = {"Sydney": '{"contradict": true}', "ACT": '{"contradict": false}'}

    async def judge(role, prompt, **kw):
        return next(v for k, v in replies.items() if k in prompt)

    with patch.object(cl, "run_agent", new=AsyncMock(return_value=json.dumps(
            [{k: c[k] for k in ("entity_display", "attribute")} for c in claims]))), \
         patch.object(structured, "extract_claims",
                      new=AsyncMock(side_effect=lambda n, *a: [c for c in claims if c["node_id"] == n])), \
         patch.object(structured, "run_agent", side_effect=judge) as llm:
        conflicts = await structured.arbitrate({"a": "x", "b": "y"}, {}, {})
    assert llm.call_count == 2
    assert [c["label"] for c in conflicts] == ["Australia capital"]
    assert conflicts[0]["sides"][0]["value"] in ("Canberra", "Sydney")
    assert "different values" in conflicts[0]["explanation"]


async def test_arbitrate_end_to_end_and_extraction_failure_is_logged():
    replies = {
        "A": json.dumps([{"entity": "Tesla", "attribute": "revenue", "period": "2023", "value": 96.77,
                          "scale": "billion", "unit": "USD", "quote": "x [1]"}]),
        "B": json.dumps([{"entity": "Tesla Inc", "attribute": "revenues", "period": "FY2023", "value": 97.69,
                          "scale": "billion", "unit": "USD", "quote": "y"}]),
    }

    async def fake(role, prompt, **kw):
        if "BROKEN" in prompt:
            raise ValueError("bad json")
        return replies["A"] if "AAA" in prompt else replies["B"]

    events = []

    async def emit(t, p):
        events.append(t)

    outputs = {"n1": "AAA Tesla 96.77 [1]\n\n---\nSources\n[1] SEC - https://data.sec.gov/x",
               "n2": "BBB Tesla 97.69", "n3": "BROKEN 5.5"}
    with patch.object(cl, "run_agent", side_effect=fake):
        conflicts = await structured.arbitrate(outputs, {"n1": "research", "n2": "research", "n3": "drafting"},
                                               {"n1": "research-v1", "n2": "research-v2", "n3": "drafting-v1"}, emit)
    assert len(conflicts) == 1 and conflicts[0]["policy"] == "source authority"
    assert events.count("claims_extracted") == 2 and "arbitration_error" in events


# ---------- human approval gate ----------

def _conflict():
    claims = [claim("n1", 96.77, sources=[SEC], agent="research-v1"), claim("n2", 97.69, agent="research-v2")]
    return structured.find_conflicts(claims, {"n1": "research", "n2": "research"})


def test_only_the_origin_of_a_wrong_figure_is_penalised():
    claims = [claim("n1", 96.77, sources=[SEC], agent="research-v1"), claim("n2", 97.69, agent="research-v2"),
              claim("n3", 97.69, agent="drafting-v1")]
    conflicts = structured.find_conflicts(claims, {"n1": "research", "n2": "research", "n3": "drafting"})
    _, _, winner, losers = resolution.resolve(conflicts, "c1", 0)
    plan = [{"id": "n1", "depends_on": []}, {"id": "n2", "depends_on": []}, {"id": "n3", "depends_on": ["n2"]}]
    ups = resolution.reputation_updates(winner, losers, plan)
    assert {a for a, q, _ in ups if q == 0.0} == {"research-v2"}   # drafting-v1 only repeated n2


def test_resolve_and_reputation_weights():
    conflicts, c, winner, losers = resolution.resolve(_conflict(), "c1", 0, "SEC is official")
    assert c["status"] == "resolved" and c["resolution"]["agreed_with_recommendation"]
    ups = resolution.reputation_updates(winner, losers)
    assert ("research-v1", 1.0, "won a reviewed conflict") in ups
    assert ups.count(("research-v2", 0.0, "lost a reviewed conflict")) == 2
    assert resolution.run_status_after(conflicts, "needs_review") == "complete"
    assert "96.77" in resolution.correction_instruction(c, winner, losers[0])
    with pytest.raises(resolution.ResolutionError):
        resolution.resolve(conflicts, "c1", 0)            # already resolved
    with pytest.raises(resolution.ResolutionError):
        resolution.resolve(_conflict(), "c1", 5)           # bad choice
    with pytest.raises(resolution.ResolutionError):
        resolution.resolve(_conflict(), "c9", 0)           # unknown id


async def test_recorder_resume_continues_sequence():
    init_db()
    run_id = crud.create_run("q")
    rec = RunRecorder(run_id)
    await rec("plan_created", {})
    await rec("run_finished", {})
    later = RunRecorder.resume(run_id)
    await later("conflict_resolved", {})
    assert [e["seq"] for e in crud.get_run(run_id)["events"]] == [1, 2, 3]


def test_resolve_endpoint_updates_run_reputation_and_can_rerun():
    import main
    init_db()
    run_id = crud.create_run("q")
    crud.finish_run(run_id, [{"id": "n1", "agent": "research", "depends_on": []},
                             {"id": "n2", "agent": "research", "depends_on": []}],
                    "needs_review", _conflict(), time.time())
    fork = AsyncMock(return_value={"run_id": "child"})
    with patch.object(main, "update_score", return_value={"mean": 0.7}) as upd, \
         patch.object(main, "_fork", new=fork):
        client = TestClient(main.app)
        bad = client.post(f"/runs/{run_id}/conflicts/c1/resolve", json={"choice": 3})
        ok = client.post(f"/runs/{run_id}/conflicts/c1/resolve", json={"choice": 0, "rerun": True})
    assert bad.status_code == 422
    body = ok.json()
    assert body["run_status"] == "complete" and body["fork"] == {"run_id": "child"}
    assert fork.await_args.args[1] == "n2" and "96.77" in fork.await_args.kwargs["instruction"]
    assert upd.call_count == 3
    data = crud.get_run(run_id)
    assert data["run"]["status"] == "complete" and data["run"]["conflicts"][0]["status"] == "resolved"
    assert {e["type"] for e in data["events"]} >= {"conflict_resolved", "reputation_updated"}


def test_auto_resolution_only_for_clear_cases_and_can_be_switched_off():
    web = {"id": 2, "title": "Blog", "url": "https://example.com/post"}
    claims = [claim("n1", 96.77, sources=[SEC]), claim("n2", 97.69, sources=[web])]
    (c,) = structured.find_conflicts(claims, {"n1": "research", "n2": "research"})
    assert c["status"] == "open"            # web source (0.5) is not low-stakes enough to decide alone
    claims = [claim("n1", 96.77, sources=[SEC]), claim("n2", 97.69)]
    (c,) = structured.find_conflicts(claims, {"n1": "research", "n2": "research"}, auto=False)
    assert c["status"] == "open" and c["resolution"] is None


def test_a_person_can_override_an_automatic_decision():
    conflicts = _conflict()
    assert conflicts[0]["status"] == "auto_resolved"
    _, c, winner, _ = resolution.resolve(conflicts, "c1", 1, "the analyst figure is newer")
    assert c["status"] == "resolved" and c["resolution"]["by"] == "person"
    assert c["resolution"]["overrode_policy"] == "$96.77 billion" and winner["value"] == "$97.69 billion"


async def test_auto_resolved_conflict_does_not_stop_the_run_and_penalises_once():
    from orchestration import executor
    plan = [{"id": "n1", "agent": "research", "depends_on": []}, {"id": "n2", "agent": "research", "depends_on": []}]
    auto = _conflict()                       # SEC vs uncited -> auto_resolved
    events = []

    async def emit(t, p):
        events.append((t, p))

    with patch.object(executor, "_dispatch", new=AsyncMock(return_value="x")), \
         patch.object(executor, "route", side_effect=lambda c: (c[0], {"reason": "x"})), \
         patch.object(executor, "update_score", return_value={"mean": 0.7}) as upd, \
         patch.object(executor, "arbitrate", new=AsyncMock(return_value=auto)):
        result = await executor.execute_plan(plan, "q", emit=emit)
    assert result["status"] == "complete"                          # no human gate for a low-stakes conflict
    assert any(t == "conflict_auto_resolved" for t, _ in events)
    zero = [c for c in upd.call_args_list if c.args[0] == "research-v2" and c.kwargs.get("quality") == 0.0]
    assert len(zero) == 1                                          # one observation (a person's decision counts twice)
