import json
from unittest.mock import AsyncMock, patch
from agents import factcheck_tools as fc

DRAFT = """Task: Compare Tesla and Ford revenue
n2: ## Revenue
| Tesla | 96.77 billion [1] |
Tesla earned $96.77 billion in 2023 [1]. Ford earned $200.5 billion in 2023 [2]. GM grew fast [3].
Both are large carmakers.

---
Sources
[1] SEC EDGAR 10-K data: Tesla, Inc. (TSLA) annual revenue - https://data.sec.gov/api/xbrl/x.json
[2] Ford - Annual Report 2023 - https://ford.com/ar2023
[3] Some PDF - https://example.com/gm.pdf

Citation check: passed. 2 figure(s), all cited and found in the research; 2 source(s) cited.
n3: **Chart: Revenue** (bar)
```vega-lite
{"values": [1]}
```"""

TEXTS = {
    "https://data.sec.gov/api/xbrl/x.json": "fiscal year ended 2023-12-31: $96.77 billion",
    "https://ford.com/ar2023": "Ford total revenue in 2023 was $176.19 billion, up 11 percent.",
    "https://example.com/gm.pdf": "",
}


def _fake_fetch(url):
    return TEXTS[url]


def test_extract_claims_skips_sources_checks_and_uncited_lines():
    claims = fc.extract_claims(fc.strip_chart_blocks(DRAFT))
    texts = [c["text"] for c in claims]
    assert len(claims) == 4
    assert texts[0] == "Tesla; 96.77 billion [1]"
    assert not any("SEC EDGAR" in t or "Citation check" in t or "carmakers" in t for t in texts)
    assert claims[2]["sources"] == [2]


def test_claim_figures():
    assert fc.claim_figures("Ford earned $200.5 billion in 2023 [2], a 5 % rise") == ["200.5", "5"]


async def test_fact_check_end_to_end():
    llm_reply = json.dumps([
        {"id": 1, "verdict": "supported", "quote": "$96.77 billion", "note": ""},
        {"id": 2, "verdict": "supported", "quote": "$96.77 billion", "note": ""},
        {"id": 3, "verdict": "supported", "quote": "revenue in 2023", "note": "model too lenient"},
    ])
    with patch.object(fc, "fetch_source_text", new=AsyncMock(side_effect=_fake_fetch)), \
         patch.object(fc, "run_agent", new=AsyncMock(return_value=llm_reply)) as llm:
        out = await fc.fact_check(DRAFT)
    assert llm.await_count == 1
    sent = llm.await_args.args[1]
    assert "Claim 4" not in sent                     # unreadable source is not sent to the LLM
    assert "2 supported, 1 unsupported, 0 contradicted, 1 unverifiable" in out
    assert "200.5 not found in cited source" in out   # code overrides the lenient LLM verdict
    assert "cited source could not be read" in out
    assert "Claims needing attention: #3." in out


async def test_contradiction_is_reported():
    llm_reply = '[{"id": 3, "verdict": "contradicted", "quote": "$176.19 billion", "note": "different value"}]'
    with patch.object(fc, "fetch_source_text", new=AsyncMock(side_effect=_fake_fetch)), \
         patch.object(fc, "run_agent", new=AsyncMock(return_value=llm_reply)):
        out = await fc.fact_check(DRAFT)
    assert "❌ contradicted" in out and '"$176.19 billion" [2]' in out
    assert "no verdict returned" in out


async def test_no_cited_claims_does_not_call_llm():
    with patch.object(fc, "run_agent", new=AsyncMock()) as llm:
        out = await fc.fact_check("Task: x\nn2: A draft with no citations at all.")
    assert llm.await_count == 0
    assert "no cited claims" in out


def test_code_blocks_are_not_claims():
    claims = fc.extract_claims("n2: Revenue was $96.77 billion [1].\n```\nTesla ███ 96.8B [1]\n```")
    assert [c["text"] for c in claims] == ["Revenue was $96.77 billion [1]."]
