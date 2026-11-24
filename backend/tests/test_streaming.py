import asyncio
import contextvars
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from agents import base_agent, usage
from orchestration import executor
from orchestration.live_stream import LiveStream


class Chunk(SimpleNamespace):
    def __add__(self, other):
        um = None
        if self.usage_metadata or other.usage_metadata:
            um = {"input_tokens": 12, "output_tokens": 5}
        return Chunk(content=self.content + other.content, usage_metadata=um)


class FakeLLM:
    async def astream(self, prompt):
        for piece in ["Solar ", "panels ", "turn ", "light ", "into ", "power."]:
            await asyncio.sleep(0)
            yield Chunk(content=piece, usage_metadata=None)
        yield Chunk(content="", usage_metadata={"input_tokens": 12, "output_tokens": 5})

    async def ainvoke(self, prompt):
        raise AssertionError("must stream when a sink is set")


async def test_run_agent_streams_and_still_records_usage():
    events = []

    async def run():
        base_agent.set_stream_sink(events.append)
        ledger = usage.start_ledger()
        with patch.object(base_agent, "_make_llm", return_value=FakeLLM()):
            out = await base_agent.run_agent("drafting", "x", provider="groq", model="m")
        return out, ledger

    out, ledger = await contextvars.copy_context().run(run)
    assert out == "Solar panels turn light into power."
    assert events[0]["start"] and events[-1]["end"]
    assert "".join(e["delta"] for e in events if "delta" in e) == out
    assert ledger[0]["tokens_out"] == 5 and ledger[0]["estimated"] is False


async def test_live_stream_batches_in_order():
    sent = []

    async def cb(payload):
        await asyncio.sleep(0)   # yields, so unordered sends would interleave
        sent.append(payload)

    live = LiveStream("n2", cb, interval=10)   # long interval: deltas are batched until the end
    live({"call": 1, "role": "drafting", "start": True})
    for word in ["a", "b", "c"]:
        live({"call": 1, "role": "drafting", "delta": word})
    live({"call": 1, "role": "drafting", "end": True})
    await live.drain()
    assert [list(p)[-1] for p in sent] == ["start", "delta", "end"]
    assert sent[1]["delta"] == "abc" and all(p["node_id"] == "n2" for p in sent)


async def test_executor_streams_per_node_but_stores_nothing_partial():
    messages, events = [], []

    async def stream(p):
        messages.append(p)

    async def emit(t, p):
        events.append(t)

    async def dispatch(skill, prompt, manifest):
        sink = base_agent._stream_sink.get()
        sink({"call": 9, "role": skill, "start": True})
        sink({"call": 9, "role": skill, "delta": f"{skill} text"})
        sink({"call": 9, "role": skill, "end": True})
        return f"{skill} text"

    plan = [{"id": "n1", "agent": "drafting", "depends_on": []}, {"id": "n2", "agent": "chart", "depends_on": []}]
    with patch.object(executor, "_dispatch", new=dispatch), \
         patch.object(executor, "update_score", return_value={"mean": 0.7}), \
         patch.object(executor, "route", side_effect=lambda c: (c[0], {"reason": "x"})), \
         patch.object(executor, "arbitrate", new=AsyncMock(return_value=[])):
        await executor.execute_plan(plan, "q", emit=emit, stream=stream)
    deltas = {m["node_id"]: m["delta"] for m in messages if "delta" in m}
    assert deltas == {"n1": "drafting text", "n2": "chart text"}
    assert not any("stream" in e or "delta" in e for e in events)
