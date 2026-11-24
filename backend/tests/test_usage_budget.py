import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from agents import usage
from orchestration import executor
from orchestration.budget import Budget
from registry.registry import REGISTRY

PLAN = [{"id": "n1", "agent": "research", "depends_on": []},
        {"id": "n2", "agent": "drafting", "depends_on": ["n1"]},
        {"id": "n3", "agent": "chart", "depends_on": ["n1"]}]


def fake_result(text, tin=None, tout=None):
    meta = {"input_tokens": tin, "output_tokens": tout} if tin is not None else None
    return SimpleNamespace(content=text, usage_metadata=meta)


# ---------- ledger ----------

def test_ledger_records_reported_and_estimated_usage():
    ledger = usage.start_ledger()
    usage.record_call("groq", "openai/gpt-oss-120b", "p" * 400, fake_result("ok", 1000, 500), time.time())
    usage.record_call("gemini", "unknown-model", "p" * 400, fake_result("x" * 80), time.time())
    s = usage.summarise(ledger)
    assert s["llm_calls"] == 2 and s["tokens_in"] == 1000 + 100 and s["tokens_out"] == 500 + 20
    assert s["tokens_estimated"] is True
    assert s["cost_usd"] == pytest.approx((1000 * 0.15 + 500 * 0.60) / 1e6 + (100 * 0.20 + 20 * 0.80) / 1e6)


def test_no_ledger_means_no_recording():
    async def outside():
        usage.record_call("groq", "m", "p", fake_result("x", 1, 1), time.time())
    asyncio.run(outside())   # a fresh context has no ledger: must not raise


async def test_parallel_nodes_keep_separate_ledgers():
    async def node(n):
        ledger = usage.start_ledger()
        for _ in range(n):
            await asyncio.sleep(0)
            usage.record_call("groq", "openai/gpt-oss-20b", "p", fake_result("x", 10, 10), time.time())
        return len(ledger)
    assert await asyncio.gather(node(1), node(3), node(2)) == [1, 3, 2]


# ---------- budget governor ----------

def test_budget_modes_and_economy_pool():
    b = Budget(1.0)
    assert b.add(0.5) is None and b.mode == "normal"
    assert b.add(0.35) == "economy"
    assert b.filter_pool(["chart-v1", "chart-v2"], REGISTRY) == ["chart-v2"]   # gpt-oss-20b is cheaper
    assert b.add(0.2) == "exhausted" and b.exhausted
    off = Budget(None)
    assert off.add(100) is None and off.filter_pool(["chart-v1", "chart-v2"], REGISTRY) == ["chart-v1", "chart-v2"]


def _patches(agent_fn):
    return [patch.object(executor, "run_agent", side_effect=agent_fn),
            patch.object(executor, "grounded_research", new=None),
            patch.object(executor, "update_score", return_value={"mean": 0.7}),
            patch.object(executor, "route", side_effect=lambda c: (c[0], {"reason": "first"})),
            patch.object(executor, "arbitrate", new=AsyncMock(return_value=[]))]


async def _run(agent_fn, **kw):
    events = []

    async def emit(t, p):
        events.append((t, p))

    async def dispatch(skill, prompt, manifest):
        return await agent_fn(skill, prompt, manifest.model)

    with patch.object(executor, "_dispatch", new=dispatch), \
         patch.object(executor, "update_score", return_value={"mean": 0.7}) as upd, \
         patch.object(executor, "route", side_effect=lambda c: (c[0], {"reason": "first"})), \
         patch.object(executor, "arbitrate", new=AsyncMock(return_value=[])):
        result = await executor.execute_plan(PLAN, "q", emit=emit, **kw)
    return result, events, upd


async def costly(skill, prompt, model):
    usage.record_call("groq", model, prompt, fake_result(f"{skill} out", 400_000, 400_000), time.time())
    return f"{skill} out"


async def test_usage_is_attached_to_nodes_and_run_totals():
    result, events, _ = await _run(costly)
    u = result["usage"]
    assert set(u["nodes"]) == {"n1", "n2", "n3"} and u["total"]["llm_calls"] == 3
    assert result["node_status"]["n1"]["usage"]["tokens_in"] == 400_000
    assert [p for t, p in events if t == "run_finished"][0]["usage"]["total"] == u["total"]


async def test_budget_downgrades_then_skips():
    # n1 (gpt-oss-120b, 0.4M in + 0.4M out) costs $0.30: with a $0.35 budget that is economy mode
    result, events, _ = await _run(costly, budget_usd=0.35)
    kinds = [t for t, _ in events]
    assert "budget_economy" in kinds and "budget_downgrade" in kinds
    downgrade = next(p for t, p in events if t == "budget_downgrade")
    # cheapest per skill in PRICES: the local model on the laptop costs nothing per token
    assert downgrade["to"] in (["drafting-local"], ["chart-local"])
    # the downgraded nodes run on the free local model, so the budget is never used up
    assert "budget_exhausted" not in kinds
    assert result["usage"]["budget"]["mode"] == "economy" and result["status"] == "complete"


async def test_exhausted_budget_skips_unstarted_nodes():
    result, events, _ = await _run(costly, budget_usd=0.01)
    assert result["node_status"]["n1"]["status"] == "done"
    assert result["node_status"]["n2"]["status"] == "skipped" and "budget" in result["node_status"]["n2"]["error"]
    assert result["status"] == "partial"


async def test_timeout_reassigns_without_penalty():
    calls = []

    async def slow_then_fast(skill, prompt, model):
        calls.append(model)
        if skill == "research" and len([c for c in calls if c]) == 1:
            await asyncio.sleep(1)
        return f"{skill} out"

    with patch.object(executor, "NODE_TIMEOUT_S", 0.05), patch.object(executor, "BACKOFF_SECONDS", 0):
        result, events, upd = await _run(slow_then_fast)
    n1 = result["node_status"]["n1"]
    assert n1["status"] == "done" and n1["attempts"] == 2 and n1["agent"] == "research-v2"
    failed = [p for t, p in events if t == "node_attempt_failed"]
    assert failed[0]["agent"] == "research-v1" and failed[0]["infra"] and "timed out" in failed[0]["error"]
    assert all(c.kwargs.get("quality") != 0.0 for c in upd.call_args_list)
