import contextvars
from unittest.mock import AsyncMock, patch

import config
from agents import base_agent
from orchestration import executor

PLAN = [{"id": "n1", "agent": "chart", "depends_on": []}]


def test_local_model_needs_no_key_and_is_the_last_fallback(monkeypatch):
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    llm = base_agent._make_llm("ollama")
    assert llm.model_name == config.LOCAL_MODEL
    assert llm.request_timeout >= base_agent.LOCAL_TIMEOUT_S
    assert config.FALLBACK_CHAIN[-1] == "ollama"


async def _calls_in(local: bool, role="chart", provider="groq", model="openai/gpt-oss-120b"):
    seen = []

    class FakeLLM:
        def __init__(self, p, m):
            self.p, self.m = p, m

        async def ainvoke(self, prompt):
            seen.append((self.p, self.m))
            raise RuntimeError("429 rate limit")   # force the whole chain to be tried

    def make(p, m=None, timeout=25):
        return FakeLLM(p, m)

    async def run():
        base_agent.force_provider("ollama" if local else None)
        try:
            await base_agent.run_agent(role, "x", provider=provider, model=model)
        except RuntimeError:
            pass

    with patch.object(base_agent, "_make_llm", side_effect=make):
        await contextvars.copy_context().run(lambda: run())   # isolated context
    return seen


async def test_local_mode_sends_every_call_to_the_laptop_model():
    seen = await _calls_in(local=True)
    assert seen == [("ollama", config.LOCAL_MODEL)]   # the cloud model name is not reused locally


async def test_normal_mode_tries_cloud_first_and_local_last():
    seen = await _calls_in(local=False)
    assert seen[0] == ("groq", "openai/gpt-oss-120b") and seen[-1][0] == "ollama"


async def test_local_only_run_routes_only_to_local_agents():
    chosen = []

    def route(pool):
        chosen.append(list(pool))
        return pool[0], {"reason": "first"}

    with patch.object(executor, "_dispatch", new=AsyncMock(return_value="All 1 values were checked")), \
         patch.object(executor, "route", side_effect=route), \
         patch.object(executor, "update_score", return_value={"mean": 0.7}), \
         patch.object(executor, "arbitrate", new=AsyncMock(return_value=[])):
        async def run():
            return await executor.execute_plan(PLAN, "q", local_only=True)
        result = await contextvars.copy_context().run(run)
    assert chosen == [["chart-local"]] and result["node_status"]["n1"]["agent"] == "chart-local"
