"""Chart agent: turns numbers in upstream research into a validated Vega-Lite chart.

Flow:
1. The LLM only EXTRACTS data points (category, series, value) from the context as JSON.
2. Code validates the extraction against a JSON Schema.
3. Code checks that every value is grounded: it must appear in the context text
   (allowing unit scaling such as million -> billion and small rounding).
   Ungrounded points are dropped and reported.
4. Code (not the LLM) builds the Vega-Lite spec, so the spec is always well-formed.
If validation fails, the LLM gets one retry with the error fed back.
The output is a string: a short readable summary plus a fenced ```vega-lite block,
so it can be stored, replayed and passed downstream like every other node output.
"""
import json
import math
import re

from jsonschema import Draft202012Validator

from agents.base_agent import run_agent
from agents.grounding import context_numbers, is_grounded  # noqa: F401 (re-exported for tests)

MAX_ATTEMPTS = 2
MAX_POINTS = 40
VEGA_LITE_SCHEMA = "https://vega.github.io/schema/vega-lite/v5.json"
FENCE = "```vega-lite"

CHART_DATA_SCHEMA = {
    "type": "object",
    "required": ["title", "chart_type", "x_label", "y_label", "data"],
    "additionalProperties": False,
    "properties": {
        "title": {"type": "string", "minLength": 1, "maxLength": 120},
        "chart_type": {"enum": ["bar", "grouped_bar", "line"]},
        "x_label": {"type": "string", "minLength": 1, "maxLength": 60},
        "y_label": {"type": "string", "minLength": 1, "maxLength": 60},
        "unit": {"type": "string", "maxLength": 30},
        "data": {
            "type": "array",
            "minItems": 1,
            "maxItems": MAX_POINTS,
            "items": {
                "type": "object",
                "required": ["category", "value"],
                "additionalProperties": False,
                "properties": {
                    "category": {"type": "string", "minLength": 1, "maxLength": 60},
                    "series": {"type": "string", "maxLength": 60},
                    "value": {"type": "number"},
                },
            },
        },
    },
}
_validator = Draft202012Validator(CHART_DATA_SCHEMA)

PROMPT = """You extract chart data. Read the context and pick the numeric facts that best answer the task.
Use ONLY numbers that appear in the context. Never estimate, calculate or invent a number.
Keep every value in ONE unit (state it in "unit", e.g. "USD billions") and copy each number as written in that unit.
Choose chart_type:
- "bar": one value per category (e.g. revenue per company for one year)
- "grouped_bar": several series per category (e.g. revenue per company, series = year)
- "line": values over time (category = year or date, one series per entity)

{task}

Return ONLY JSON, no markdown, in this format:
{{"title": "...", "chart_type": "bar", "x_label": "...", "y_label": "...", "unit": "...",
 "data": [{{"category": "...", "series": "...", "value": 0.0}}]}}
"series" may be omitted for a plain bar chart."""


class ChartError(ValueError):
    """The chart agent could not produce a valid, grounded chart (counts against reputation)."""


def strip_chart_blocks(text: str) -> str:
    """Remove the Vega-Lite JSON so downstream LLM prompts only see the readable summary."""
    return re.sub(r"```vega-lite.*?```", "[chart spec omitted]", text, flags=re.S)


def parse_json(raw: str):
    raw = raw.strip()
    match = re.search(r"\{.*\}", raw, flags=re.S)
    if not match:
        raise ChartError("no JSON object in the response")
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as e:
        raise ChartError(f"invalid JSON: {e}") from e


def validate_chart_data(data) -> None:
    errors = sorted(_validator.iter_errors(data), key=lambda e: list(e.path))
    if errors:
        e = errors[0]
        where = "/".join(str(p) for p in e.path) or "root"
        raise ChartError(f"schema error at {where}: {e.message}")
    for p in data["data"]:
        if not math.isfinite(p["value"]):
            raise ChartError("non-finite value")


def ground(data: dict, context: str):
    numbers = context_numbers(context)
    kept, dropped = [], []
    for p in data["data"]:
        (kept if is_grounded(p["value"], numbers) else dropped).append(p)
    return kept, dropped


def build_spec(data: dict) -> dict:
    points = data["data"]
    unit = data.get("unit") or ""
    y_title = f'{data["y_label"]} ({unit})' if unit and unit not in data["y_label"] else data["y_label"]
    has_series = any(p.get("series") for p in points)
    values = [{"category": p["category"], "series": p.get("series") or data["y_label"],
               "value": p["value"]} for p in points]

    x = {"field": "category", "type": "ordinal" if data["chart_type"] == "line" else "nominal",
         "title": data["x_label"], "sort": None}
    y = {"field": "value", "type": "quantitative", "title": y_title}
    tooltip = [{"field": "category", "title": data["x_label"]},
               {"field": "series", "title": "Series"},
               {"field": "value", "title": y_title, "format": ",.2f"}]

    spec = {
        "$schema": VEGA_LITE_SCHEMA,
        "title": data["title"],
        "width": "container",
        "height": 260,
        "data": {"values": values},
        "encoding": {"x": x, "y": y, "tooltip": tooltip},
    }
    if data["chart_type"] == "line":
        spec["mark"] = {"type": "line", "point": True}
        if has_series:
            spec["encoding"]["color"] = {"field": "series", "type": "nominal", "title": "Series"}
    else:
        spec["mark"] = {"type": "bar"}
        if has_series:
            spec["encoding"]["color"] = {"field": "series", "type": "nominal", "title": "Series"}
            if data["chart_type"] == "grouped_bar":
                spec["encoding"]["xOffset"] = {"field": "series"}
    return spec


def render_output(data: dict, spec: dict, dropped: list) -> str:
    unit = data.get("unit") or ""
    lines = [f'**Chart: {data["title"]}** ({data["chart_type"].replace("_", " ")})', "",
             f'| {data["x_label"]} | Series | Value{f" ({unit})" if unit else ""} |', "|---|---|---|"]
    for p in data["data"]:
        lines.append(f'| {p["category"]} | {p.get("series") or "-"} | {p["value"]:,} |')
    lines.append("")
    lines.append(f"All {len(data['data'])} values were checked against the numbers in the research context.")
    if dropped:
        removed = ", ".join(f'{p["category"]} {p.get("series") or ""} = {p["value"]}'.replace("  ", " ")
                            for p in dropped)
        lines.append(f"Removed {len(dropped)} value(s) not found in the context: {removed}.")
    lines += ["", FENCE, json.dumps(spec, indent=1), "```"]
    return "\n".join(lines)


async def build_chart(prompt: str, provider: str = None, model: str = None) -> str:
    context = strip_chart_blocks(prompt)
    last_error = None
    for _ in range(MAX_ATTEMPTS):
        ask = PROMPT.format(task=context)
        if last_error:
            ask += f"\n\nYour previous answer was rejected: {last_error}. Fix it and return only JSON."
        raw = await run_agent("chart", ask, provider=provider, model=model)
        try:
            data = parse_json(raw)
            validate_chart_data(data)
            kept, dropped = ground(data, context)
            if not kept:
                raise ChartError("none of the values appear in the context; copy numbers exactly as written")
            data["data"] = kept
            return render_output(data, build_spec(data), dropped)
        except ChartError as e:
            last_error = str(e)
            print(f"[CHART] rejected: {last_error}")
    raise ChartError(f"chart agent failed after {MAX_ATTEMPTS} attempts: {last_error}")
