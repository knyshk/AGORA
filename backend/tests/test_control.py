import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from orchestration import executor
from orchestration.control import ControlError, RunControl

PLAN = [{"id": "n2", "agent": "drafting", "depends_on": []},
        {"id": "n3", "agent": "chart", "depends_on": []}]


async def _run(control, script, actions):
    """script(skill, prompt, manifest) -> output; actions(control, events) runs alongside the plan."""
    events, calls = [], []

    async def emit(t, p):
        events.append((t, p))

    async def dispatch(skill, prompt, manifest):
        calls.append((skill, manifest.name, prompt))
        return await script(skill, prompt, manifest)

    with patch.object(executor, "_dispatch", new=dispatch), \
         patch.object(executor, "update_score", return_value={"mean": 0.7}) as upd, \
         patch.object(executor, "route", side_effect=lambda c: (c[0], {"reason": "first"})), \
         patch.object(executor, "arbitrate", new=AsyncMock(return_value=[])):
        result, _ = await asyncio.gather(executor.execute_plan(PLAN, "q", emit=emit, control=control),
                                         actions(control, events))
    return result, events, calls, upd


async def _until(events, kind, node):
    while not any(t == kind and p.get("node_id") == node for t, p in events):
        await asyncio.sleep(0.005)


async def test_paused_node_waits_while_its_sibling_finishes():
    control = RunControl()
    control.pause("n2")
    order = []

    async def script(skill, prompt, manifest):
        order.append(skill)
        return f"{skill} out"

    async def actions(control, events):
        await _until(events, "node_finished", "n3")
        assert not any(t == "node_started" and p["node_id"] == "n2" for t, p in events)
        control.resume("n2", instruction="be brief")

    result, events, calls, _ = await _run(control, script, actions)
    assert order == ["chart", "drafting"] and result["status"] == "complete"
    assert "Instruction from a person in the session: be brief" in calls[-1][2]
    assert any(t == "node_waiting_paused" for t, _ in events)


async def test_redirect_cancels_the_running_call_and_restarts_without_penalty():
    control = RunControl()
    started = asyncio.Event()

    async def script(skill, prompt, manifest):
        if skill == "drafting" and "Instruction from a person" not in prompt:
            started.set()
            await asyncio.sleep(10)          # a long call that gets interrupted
        return f"{skill} out"

    async def actions(control, events):
        await started.wait()
        control.redirect("n2", "focus on 2023 only")

    result, events, calls, upd = await _run(control, script, actions)
    n2 = result["node_status"]["n2"]
    assert n2["status"] == "done" and n2["attempts"] == 1
    assert ("node_interrupted", {"node_id": "n2", "agent": "drafting-v1", "reason": "redirected"}) in events
    assert "focus on 2023 only" in [c for c in calls if c[0] == "drafting"][-1][2]
    assert all(c.kwargs.get("quality") != 0.0 for c in upd.call_args_list)   # no reputation penalty


async def test_reassign_switches_the_agent():
    control = RunControl()
    started = asyncio.Event()

    async def script(skill, prompt, manifest):
        if manifest.name == "drafting-v1":
            started.set()
            await asyncio.sleep(10)
        return f"{manifest.name} out"

    async def actions(control, events):
        await started.wait()
        control.reassign("n2", "drafting-local")

    result, events, calls, _ = await _run(control, script, actions)
    assert result["outputs"]["n2"] == "drafting-local out"
    routed = [p for t, p in events if t == "agent_routed" and p["node_id"] == "n2"]
    assert "reassigned" in routed[-1]["reason"]


def test_actions_on_a_finished_node_are_refused():
    control = RunControl()
    control.finished("n2")
    for action in (lambda: control.pause("n2"), lambda: control.redirect("n2", "x"),
                   lambda: control.reassign("n2", "a"), lambda: control.resume("n2")):
        with pytest.raises(ControlError):
            action()
    with pytest.raises(ControlError):
        RunControl().redirect("n9", "  ")
