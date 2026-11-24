import time
from unittest.mock import patch

from db import crud
from db.database import init_db
from db.recorder import RunRecorder
from metrics import overview as ov

USAGE = {"llm_calls": 2, "tokens_in": 100, "tokens_out": 50, "cost_usd": 0.001, "tokens_estimated": False,
         "llm_latency_s": 1.0, "models": ["m"]}


async def _make_run(status, events, conflicts=None):
    run_id = crud.create_run("metrics test")
    rec = RunRecorder(run_id)
    for kind, payload in events:
        await rec(kind, payload)
    crud.finish_run(run_id, [], status, conflicts or [], time.time() - 3)
    return run_id


async def test_overview_aggregates_stored_events_only():
    init_db()
    await _make_run("complete", [
        ("node_finished", {"node_id": "n1", "skill": "chart", "agent": "chart-v1", "duration_s": 2.0,
                           "quality": 1.0, "usage": USAGE}),
        ("node_attempt_failed", {"node_id": "n2", "agent": "chart-v2", "infra": True, "error": "429"}),
        ("node_finished", {"node_id": "n2", "skill": "chart", "agent": "chart-v1", "duration_s": 4.0,
                           "quality": 0.5, "usage": USAGE}),
        ("reputation_updated", {"agent": "chart-v1", "quality": 1.0, "source": "output_check", "after": {"mean": 0.8}}),
        ("node_finished", {"node_id": "n3", "skill": "drafting", "agent": "human:Bob", "duration_s": 9.0}),
        ("run_finished", {"status": "complete", "usage": {"total": {"cost_usd": 0.002}}}),
    ])
    conflict = {"id": "c1", "status": "resolved", "policy": "source authority",
                "resolution": {"agreed_with_recommendation": True}}
    await _make_run("failed", [
        ("node_failed", {"node_id": "n1", "skill": "chart", "agent": "chart-v1", "duration_s": 1.0, "usage": USAGE}),
    ], conflicts=[conflict])

    with patch.object(ov, "get_stats", return_value={"mean": 0.8, "ci95": [0.6, 1.0], "n": 3}):
        data = ov.overview(days=1)

    chart_v1 = next(a for a in data["agents"] if a["agent"] == "chart-v1")
    assert chart_v1["done"] >= 2 and chart_v1["failed"] >= 1
    chart_v2 = next(a for a in data["agents"] if a["agent"] == "chart-v2")
    assert chart_v2["infra_failures"] >= 1
    assert not any(a["agent"].startswith("human:") for a in data["agents"])
    assert data["humans"]["nodes_written_by_people"] >= 1
    assert data["runs"]["by_status"]["failed"] >= 1 and data["runs"]["cost_usd"] >= 0.002
    assert data["conflicts"]["resolved"] >= 1 and data["conflicts"]["reviewer_agreed_with_recommendation"] >= 1
    assert data["reputation"]["chart-v1"][-1]["trust"] == 0.8
    assert data["audit"]["ok"] in (True, False) and "by_action" in data["audit"]


def test_mean_ignores_missing_values():
    assert ov._mean([1.0, None, 0.5]) == 0.75 and ov._mean([None]) is None
