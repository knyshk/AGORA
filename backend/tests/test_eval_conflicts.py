from collections import Counter
from unittest.mock import AsyncMock, patch

from bench import eval_conflicts as ev


def test_dataset_is_balanced_with_unique_ids():
    pairs = ev.load_pairs()
    assert len(pairs) >= 60
    assert Counter(p["label"] for p in pairs) == {True: 32, False: 32}
    assert len({p["id"] for p in pairs}) == len(pairs)


def test_metrics_and_wilson():
    rows = [{"label": True, "category": "x", "m": {"pred": True, "error": None, "latency_s": 1}},
            {"label": True, "category": "x", "m": {"pred": False, "error": "e", "latency_s": 1}},
            {"label": False, "category": "y", "m": {"pred": True, "error": None, "latency_s": 1}},
            {"label": False, "category": "y", "m": {"pred": False, "error": None, "latency_s": 1}}]
    s = ev.metrics(rows, "m")
    assert (s["tp"], s["fp"], s["fn"], s["tn"]) == (1, 1, 1, 1)
    assert s["precision"] == 0.5 and s["recall"] == 0.5 and s["f1"] == 0.5 and s["errors"] == 1
    assert ev.wilson(0, 0) is None and ev.wilson(5, 10)[0] < 0.5 < ev.wilson(5, 10)[1]


async def test_method_errors_count_as_no_conflict():
    with patch.object(ev, "detect_conflict", new=AsyncMock(side_effect=ValueError("bad json"))):
        out = await ev.run_method("old", {"a": "x", "b": "y"})
    assert out["pred"] is False and "bad json" in out["error"]


async def test_rate_limits_are_retried_then_excluded():
    calls = []

    async def flaky(pair):
        calls.append(1)
        raise RuntimeError("All providers exhausted. Error code: 429")
    with patch.dict(ev.METHODS, {"old": flaky}):
        out = await ev.run_method("old", {"a": "x", "b": "y"}, wait=0)
    assert out["infra"] and len(calls) == ev.INFRA_RETRIES + 1
    rows = [{"label": True, "category": "x", "m": out},
            {"label": True, "category": "x", "m": {"pred": True, "error": None, "latency_s": 1}}]
    s = ev.metrics(rows, "m")
    assert s["n"] == 1 and s["excluded_infra"] == 1 and s["recall"] == 1.0
