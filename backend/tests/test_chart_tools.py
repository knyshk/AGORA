import json
import pytest
from unittest.mock import AsyncMock, patch
from agents import chart_tools as ct
from agents.chart_tools import ChartError

CONTEXT = """Task: Compare Tesla and Ford revenue
n1: Tesla revenue was $81.46 billion in 2022 and $96.77 billion in 2023 [1].
Ford reported total revenue of $176,191 million in 2023 [2]."""

GOOD = {
    "title": "Revenue 2023", "chart_type": "bar", "x_label": "Company", "y_label": "Revenue",
    "unit": "USD billions",
    "data": [{"category": "Tesla", "value": 96.77}, {"category": "Ford", "value": 176.19}],
}


def _spec_from(output: str) -> dict:
    block = output.split(ct.FENCE, 1)[1].split("```", 1)[0]
    return json.loads(block)


def test_schema_accepts_valid_data():
    ct.validate_chart_data(GOOD)


@pytest.mark.parametrize("bad", [
    {**GOOD, "chart_type": "pie"},
    {**GOOD, "data": []},
    {**GOOD, "data": [{"category": "Tesla", "value": "96.77"}]},
    {k: v for k, v in GOOD.items() if k != "title"},
    {**GOOD, "extra": 1},
])
def test_schema_rejects_invalid_data(bad):
    with pytest.raises(ChartError):
        ct.validate_chart_data(bad)


def test_grounding_handles_commas_and_unit_scaling():
    nums = ct.context_numbers(CONTEXT)
    assert ct.is_grounded(96.77, nums)
    assert ct.is_grounded(176.19, nums)      # 176,191 million -> 176.19 billion
    assert ct.is_grounded(81_460, nums)      # billions -> millions
    assert not ct.is_grounded(120.5, nums)


def test_citation_markers_and_small_numbers_do_not_ground_scaled_values():
    nums = ct.context_numbers("Revenue grew [1] in 2 regions [3].")
    assert 1.0 not in nums and 3.0 not in nums
    assert ct.is_grounded(2, nums)
    assert not ct.is_grounded(2000, nums)


def test_ground_drops_invented_values():
    data = {**GOOD, "data": GOOD["data"] + [{"category": "GM", "value": 171.84}]}
    kept, dropped = ct.ground(data, CONTEXT)
    assert [p["category"] for p in kept] == ["Tesla", "Ford"]
    assert [p["category"] for p in dropped] == ["GM"]


def test_grouped_bar_spec_uses_series():
    data = {**GOOD, "chart_type": "grouped_bar",
            "data": [{"category": "Tesla", "series": "2022", "value": 81.46},
                     {"category": "Tesla", "series": "2023", "value": 96.77}]}
    spec = ct.build_spec(data)
    assert spec["mark"]["type"] == "bar"
    assert spec["encoding"]["xOffset"] == {"field": "series"}
    assert spec["encoding"]["color"]["field"] == "series"
    assert spec["$schema"].endswith("v5.json")
    assert len(spec["data"]["values"]) == 2


def test_line_spec():
    spec = ct.build_spec({**GOOD, "chart_type": "line"})
    assert spec["mark"] == {"type": "line", "point": True}
    assert spec["encoding"]["x"]["type"] == "ordinal"


def test_strip_chart_blocks():
    text = "summary\n```vega-lite\n{\"a\": 1}\n```\nafter"
    out = ct.strip_chart_blocks(text)
    assert "vega-lite" not in out and "summary" in out and "after" in out


async def test_build_chart_end_to_end_reports_dropped_values():
    raw = json.dumps({**GOOD, "data": GOOD["data"] + [{"category": "GM", "value": 171.84}]})
    with patch.object(ct, "run_agent", new=AsyncMock(return_value=raw)) as llm:
        out = await ct.build_chart(CONTEXT)
    assert llm.await_count == 1
    spec = _spec_from(out)
    assert [v["category"] for v in spec["data"]["values"]] == ["Tesla", "Ford"]
    assert "Removed 1 value(s)" in out and "GM" in out


async def test_build_chart_retries_with_error_then_succeeds():
    responses = ["not json at all", "```json\n" + json.dumps(GOOD) + "\n```"]
    with patch.object(ct, "run_agent", new=AsyncMock(side_effect=responses)) as llm:
        out = await ct.build_chart(CONTEXT)
    assert llm.await_count == 2
    assert "previous answer was rejected" in llm.await_args_list[1].args[1]
    assert _spec_from(out)["mark"]["type"] == "bar"


async def test_build_chart_fails_when_nothing_is_grounded():
    raw = json.dumps({**GOOD, "data": [{"category": "Tesla", "value": 999.9}]})
    with patch.object(ct, "run_agent", new=AsyncMock(return_value=raw)):
        with pytest.raises(ChartError):
            await ct.build_chart(CONTEXT)


async def test_build_chart_ignores_upstream_chart_json():
    upstream = CONTEXT + "\n```vega-lite\n{\"values\": [123456.0]}\n```"
    raw = json.dumps({**GOOD, "data": [{"category": "X", "value": 123456.0}]})
    with patch.object(ct, "run_agent", new=AsyncMock(return_value=raw)):
        with pytest.raises(ChartError):
            await ct.build_chart(upstream)
