import pytest
from unittest.mock import patch
from orchestration import executor


async def _fake_grounded(prompt, provider=None, model=None):
    return await executor.run_agent("research", prompt, provider=provider, model=model)


async def _fake_chart(prompt, provider=None, model=None):
    return await executor.run_agent("chart", prompt, provider=provider, model=model)


async def _fake_draft(prompt, provider=None, model=None):
    return await executor.run_agent("drafting", prompt, provider=provider, model=model)


async def _fake_fact_check(prompt, provider=None, model=None):
    return await executor.run_agent("fact_check", prompt, provider=provider, model=model)


@pytest.fixture(autouse=True)
def no_redis_no_sleep():
    with patch.object(executor, "update_score", return_value={"mean": 0.7}), \
         patch.object(executor, "route", side_effect=lambda c: (c[0], {"mode": "test", "reason": "first"})), \
         patch.object(executor, "BACKOFF_SECONDS", 0), \
         patch.object(executor, "grounded_research", new=_fake_grounded), \
         patch.object(executor, "build_chart", new=_fake_chart), \
         patch.object(executor, "write_draft", new=_fake_draft), \
         patch.object(executor, "fact_check", new=_fake_fact_check), \
         patch.object(executor, "detect_conflict", return_value=None):
        yield


PLAN = [
    {"id": "n1", "agent": "research", "depends_on": []},
    {"id": "n2", "agent": "drafting", "depends_on": ["n1"]},
    {"id": "n3", "agent": "chart", "depends_on": ["n1"]},
]


async def test_all_nodes_succeed():
    async def fake(role, prompt, provider=None, model=None):
        return f"{role} output"
    with patch.object(executor, "run_agent", side_effect=fake):
        result = await executor.execute_plan(PLAN, "q")
    assert result["status"] == "complete"
    assert set(result["outputs"]) == {"n1", "n2", "n3"}


async def test_failed_branch_gives_partial_result():
    async def fake(role, prompt, provider=None, model=None):
        if role == "chart":
            raise ValueError("bad output")
        return f"{role} output"
    with patch.object(executor, "run_agent", side_effect=fake):
        result = await executor.execute_plan(PLAN, "q")
    assert result["status"] == "partial"
    assert result["node_status"]["n3"]["status"] == "failed"
    assert result["node_status"]["n2"]["status"] == "done"


async def test_downstream_nodes_skipped_when_root_fails():
    async def fake(role, prompt, provider=None, model=None):
        raise ValueError("boom")
    with patch.object(executor, "run_agent", side_effect=fake):
        result = await executor.execute_plan(PLAN, "q")
    assert result["status"] == "failed"
    assert result["node_status"]["n2"]["status"] == "skipped"


async def test_retry_succeeds_on_second_attempt():
    calls = {"n": 0}
    async def fake(role, prompt, provider=None, model=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ValueError("first try fails")
        return "ok"
    with patch.object(executor, "run_agent", side_effect=fake):
        result = await executor.execute_plan([PLAN[0]], "q")
    assert result["node_status"]["n1"]["attempts"] == 2
    assert result["status"] == "complete"

async def test_initial_state_nodes_are_reused_not_rerun():
    calls = []
    async def fake(role, prompt, provider=None, model=None):
        calls.append(role)
        return f"{role} new"
    with patch.object(executor, "run_agent", side_effect=fake):
        result = await executor.execute_plan(PLAN, "q", initial_state={"n1": "old research"})
    assert "research" not in calls
    assert result["outputs"]["n1"] == "old research"
    assert result["status"] == "complete"


async def test_forced_agent_is_used():
    used = []
    async def fake(role, prompt, provider=None, model=None):
        used.append(model)
        return "ok"
    with patch.object(executor, "run_agent", side_effect=fake):
        await executor.execute_plan([PLAN[0]], "q", forced_agents={"n1": "research-v2"})
    assert used == ["gemini-3.5-flash-lite"]

async def test_quality_is_graded_and_fact_check_feeds_back_to_drafting_agent():
    plan = [
        {"id": "n1", "agent": "research", "depends_on": []},
        {"id": "n2", "agent": "drafting", "depends_on": ["n1"]},
        {"id": "n3", "agent": "fact_check", "depends_on": ["n2"]},
    ]
    outputs = {
        "research": "Answer [1].\n\n---\nSources\n[1] a - http://a",
        "drafting": "Draft [1].\nCitation check: passed. 1 figure(s)",
        "fact_check": "**Fact check: 4 cited claim(s)** — 2 supported, 0 unsupported, 2 contradicted, 0 unverifiable.",
    }
    events = []

    async def fake(role, prompt, provider=None, model=None):
        return outputs[role]

    async def emit(t, p):
        events.append((t, p))

    with patch.object(executor, "run_agent", side_effect=fake), \
         patch.object(executor, "update_score", return_value={"mean": 0.7}) as upd:
        result = await executor.execute_plan(plan, "q", emit=emit)

    assert result["node_status"]["n1"]["quality"] == 1.0
    grades = [p for t, p in events if t == "reputation_updated"]
    feedback = [g for g in grades if g["source"] == "fact_check_feedback"]
    assert len(feedback) == 1 and feedback[0]["agent"] == "drafting-v1" and feedback[0]["quality"] == 0.5
    assert upd.call_args_list[-1].kwargs["quality"] == 0.5
    assert sum(1 for t, _ in events if t == "agent_routed") == 3
