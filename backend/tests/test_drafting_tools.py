from unittest.mock import AsyncMock, patch
from agents import drafting_tools as dt

RESEARCH = """Task: Compare Tesla and Ford revenue
n1: Tesla revenue was $81.46 billion in 2022 and $96.77 billion in 2023 [1]. Ford reported $176.19 billion in 2023 [2].

---
Sources
[1] SEC EDGAR 10-K data: Tesla, Inc. (TSLA) annual revenue - https://data.sec.gov/tsla.json
[2] Ford - Annual Report 2023 - https://ford.com/ar2023
[3] Unused page - https://example.com/unused"""

GOOD = "## Revenue\nTesla earned $96.77 billion in 2023 [1]. Ford earned $176.19 billion [2]. Both are large carmakers."


def test_parse_sources_handles_dashes_in_titles():
    src = dt.parse_sources(RESEARCH)
    assert set(src) == {1, 2, 3}
    assert src[2] == ("Ford - Annual Report 2023", "https://ford.com/ar2023")


def test_cited_ids_handles_lists():
    assert dt.cited_ids("a [1] b [2, 3]") == [1, 2, 3]


def test_years_and_small_counts_are_not_data_numbers():
    assert not dt.is_data_number("2023")
    assert not dt.is_data_number("3")
    assert dt.is_data_number("96.77")
    assert dt.is_data_number("176,191")


def test_check_passes_good_draft():
    report = dt.check_draft(GOOD, dt.parse_sources(RESEARCH), RESEARCH)
    assert dt.problems(report) == []
    assert report["figures"] == 2


def test_check_flags_unknown_uncited_and_invented():
    bad = "Tesla earned $96.77 billion [7]. GM earned $171.84 billion."
    report = dt.check_draft(bad, dt.parse_sources(RESEARCH), RESEARCH)
    assert report["unknown_citations"] == [7]
    assert len(report["uncited_sentences"]) == 1
    assert report["ungrounded_numbers"] == ["171.84"]


async def test_write_draft_appends_only_cited_sources_by_code():
    with patch.object(dt, "run_agent", new=AsyncMock(return_value=GOOD)) as llm:
        out = await dt.write_draft(RESEARCH)
    assert llm.await_count == 1
    assert "[1] SEC EDGAR 10-K data" in out and "[2] Ford - Annual Report 2023" in out
    assert "example.com/unused" not in out
    assert "Citation check: passed" in out


async def test_write_draft_retries_with_problems_then_passes():
    bad = "Tesla earned $96.77 billion. Ford earned $200 billion [9]."
    with patch.object(dt, "run_agent", new=AsyncMock(side_effect=[bad, GOOD])) as llm:
        out = await dt.write_draft(RESEARCH)
    assert llm.await_count == 2
    retry_prompt = llm.await_args_list[1].args[1]
    assert "rejected" in retry_prompt and "[9]" in retry_prompt and "200" in retry_prompt
    assert "Citation check: passed" in out


async def test_write_draft_reports_problems_openly_and_strips_fake_citations():
    bad = "Tesla earned $96.77 billion [1]. GM earned $171.84 billion [9]."
    with patch.object(dt, "run_agent", new=AsyncMock(return_value=bad)) as llm:
        out = await dt.write_draft(RESEARCH)
    assert llm.await_count == dt.MAX_ATTEMPTS
    assert "NOT fully passed" in out and "171.84" in out
    assert "[9]" not in out.split("---")[0]


async def test_write_draft_without_sources_is_marked_uncited():
    context = "Task: x\nn1: NOTE: no live sources could be retrieved. Revenue was 12.5 billion."
    with patch.object(dt, "run_agent", new=AsyncMock(return_value="Revenue was 12.5 billion [1].")):
        out = await dt.write_draft(context)
    assert "uncited" in out and "[1]" not in out.split("---")[0]


def test_normalize_citation_styles():
    assert dt.normalize_citations("a [2\u2020L1-L4, 1\u2020L1-L4] b \u30101\u3011") == "a [2, 1] b [1]"


def test_percentages_count_and_form_names_do_not():
    report = dt.check_draft("Revenue rose 5 % last year. Data is from the Form 10-K.",
                            dt.parse_sources(RESEARCH), RESEARCH)
    assert len(report["uncited_sentences"]) == 1 and "5 %" in report["uncited_sentences"][0]


async def test_write_draft_accepts_dagger_citations():
    raw = "Tesla earned $96.77 billion [1\u2020L1-L4]. Ford earned $176.19 billion \u30102\u3011."
    with patch.object(dt, "run_agent", new=AsyncMock(return_value=raw)):
        out = await dt.write_draft(RESEARCH)
    assert "Citation check: passed" in out and "[1] SEC EDGAR" in out
