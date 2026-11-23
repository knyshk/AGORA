from unittest.mock import patch, AsyncMock
from agents import research_tools as rt
import pytest


@pytest.fixture(autouse=True)
def no_page_fetch():
    with patch.object(rt, "_fetch_page_text", new=AsyncMock(return_value="")):
        yield

def test_parse_queries_valid_json():
    assert rt.parse_queries('["a", "b"]', "fallback") == ["a", "b"]


def test_parse_queries_handles_code_fence():
    assert rt.parse_queries('```json\n["x"]\n```', "fb") == ["x"]


def test_parse_queries_falls_back_on_garbage():
    assert rt.parse_queries("not json", "my task") == ["my task"]


def test_dedupe_sources_removes_duplicate_urls():
    a = {"title": "A", "url": "http://a", "snippet": "s", "type": "web"}
    b = {"title": "B", "url": "http://a", "snippet": "s", "type": "web"}
    assert len(rt.dedupe_sources([[a], [b]])) == 1


async def test_grounded_research_cites_numbered_sources():
    prompts = []

    async def fake_agent(role, prompt, provider=None, model=None):
        prompts.append(prompt)
        return '["tesla revenue"]' if "search queries" in prompt else "Tesla revenue was X [1]."

    src = [{"title": "Tesla 10-K", "url": "http://sec.gov/x", "snippet": "Revenue was X.", "type": "web"}]
    with patch.object(rt, "run_agent", side_effect=fake_agent), \
         patch.object(rt, "_web_search", new=AsyncMock(return_value=src)), \
         patch.object(rt, "_wikipedia", new=AsyncMock(return_value=[])):
        out = await rt.grounded_research("Task: tesla")
    assert "[1] Tesla 10-K - http://sec.gov/x" in out
    assert "SOURCES:" in prompts[-1] and "[1] Tesla 10-K" in prompts[-1]


async def test_grounded_research_warns_when_no_sources():
    async def fake_agent(role, prompt, provider=None, model=None):
        return '["q"]' if "search queries" in prompt else "some answer"

    with patch.object(rt, "run_agent", side_effect=fake_agent), \
         patch.object(rt, "_web_search", new=AsyncMock(return_value=[])), \
         patch.object(rt, "_wikipedia", new=AsyncMock(return_value=[])):
        out = await rt.grounded_research("Task: tesla")
    assert out.startswith("NOTE: no live sources")

def test_best_chunks_prefers_relevant_passage_with_numbers():
    text = "Intro about the company history.\n\nTotal revenues were $96.8 billion in 2023, up 19 percent.\n\nContact us for press."
    terms = rt.keywords("tesla total revenues 2023")
    top = rt.best_chunks(text, terms, n=1)
    assert "96.8" in top[0]


async def test_enrich_sources_replaces_snippet_with_page_passages():
    src = [{"title": "T", "url": "http://x", "snippet": "short", "type": "web"}]
    page = "Filler text.\n\nRevenue for 2022 was $81.5 billion according to the filing."
    with patch.object(rt, "_fetch_page_text", new=AsyncMock(return_value=page)):
        out = await rt.enrich_sources(src, rt.keywords("revenue 2022 billion"))
    assert "81.5" in out[0]["snippet"]
    assert out[0]["fetched"] is True