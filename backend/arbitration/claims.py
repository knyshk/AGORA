"""Structured claims: (entity, attribute, period, value) extracted from each node's output.

- Text nodes (research, drafting): ONE LLM call per node turns figure-bearing sentences into JSON
  claims. Nodes without figures cost nothing.
- Chart nodes: claims are read straight from the validated Vega-Lite spec (no LLM).
- Fact-check nodes are skipped: a verifier quoting a source is not a competing claim.
Everything is then normalised in code (company aliases, metric synonyms, years, unit words),
so comparison is deterministic.
"""
import json
import re

from agents.base_agent import run_agent
from agents.chart_tools import strip_chart_blocks
from agents.drafting_tools import CITATION, SOURCE_LINE, cited_ids, normalize_citations, parse_sources

MAX_CLAIMS_PER_NODE = 15
SKIP_SKILLS = {"fact_check"}

SCALES = {"": 1.0, "unit": 1.0, "thousand": 1e3, "k": 1e3, "million": 1e6, "mn": 1e6, "m": 1e6,
          "billion": 1e9, "bn": 1e9, "b": 1e9, "trillion": 1e12, "tn": 1e12, "t": 1e12}

ATTRIBUTE_SYNONYMS = {
    "revenue": ["revenue", "revenues", "total revenue", "total revenues", "net sales", "sales",
                "total net sales", "turnover", "net revenue", "operating revenue"],
    "net income": ["net income", "net profit", "profit", "net earnings", "earnings"],
    "operating income": ["operating income", "operating profit"],
    "gross margin": ["gross margin", "gross profit margin"],
    "height": ["height", "elevation", "altitude"],
    "employees": ["employees", "headcount", "workforce", "staff", "number of employees", "employee count",
                  "employed", "people employed", "employment"],
    "deliveries": ["deliveries", "vehicle deliveries", "vehicles delivered"],
}
_ATTR = {syn: canon for canon, syns in ATTRIBUTE_SYNONYMS.items() for syn in syns}

ENTITY_ALIASES = {"general motors": "gm", "ford motor": "ford", "alphabet": "google", "meta platforms": "meta",
                  "toyota motor": "toyota", "mt everest": "mount everest", "everest": "mount everest"}
_ENTITY_NOISE = r"\b(inc|incorporated|corp|corporation|co|company|ltd|limited|plc|llc|group|holdings|the)\b\.?"

PROMPT = """Extract every checkable factual claim from the text below as JSON.
For each claim give:
- "entity": the company, place, person or thing (short common name, e.g. "Tesla", "Ford", "GM", "Apple", "Mount Everest")
- "attribute": what is stated about it, in lowercase (e.g. "revenue", "net income", "height", "capital",
  "chief executive", "creator", "location", "first release year", "net sales change")
- "period": the year or fiscal year it refers to as written (e.g. "2023", "fiscal 2023"), or "" if none
- "value": the number exactly as written, as a JSON number (no commas), or null for a non-numeric fact.
  Increases and decreases are signed: "fell 2.8%" -> -2.8, "rose 2.8%" -> 2.8.
  When a year IS the fact (e.g. "first released in 1991"), the value is the year and period is "".
- "text_value": for non-numeric facts, the stated value (e.g. "Canberra", "Elon Musk", "Paris"); otherwise ""
- "scale": "", "thousand", "million", "billion" or "trillion" as written
- "unit": "USD", "%", "m", "km", "people", "vehicles", ... as written ("" for non-numeric facts)
- "quote": the exact words of the sentence containing it (max 30 words)
Skip years that only say WHEN something happened, citation markers like [1], and list numbering.
Return ONLY a JSON list (max {max_claims} items), [] if there are none.

Text:
{text}"""


def normalize_entity(name: str) -> str:
    e = re.sub(_ENTITY_NOISE, " ", (name or "").lower())
    e = re.sub(r"[^a-z0-9 ]", " ", e)
    e = re.sub(r"\s+", " ", e).strip()
    return ENTITY_ALIASES.get(e, e)


def normalize_attribute(name: str) -> str:
    a = re.sub(r"[^a-z ]", " ", (name or "").lower())
    a = re.sub(r"\s+", " ", a).strip()
    return _ATTR.get(a, a)


def normalize_period(period: str) -> str:
    years = re.findall(r"(?:19|20)\d{2}", str(period or ""))
    return years[-1] if years else ""


def unit_kind(unit: str) -> str:
    u = (unit or "").lower()
    if any(c in u for c in ("usd", "$", "dollar", "eur", "€", "gbp", "£", "yen", "¥", "inr", "₹")):
        return "currency"
    if "%" in u or "percent" in u:
        return "percent"
    if u in ("m", "metre", "metres", "meter", "meters", "km", "ft", "feet"):
        return "length"
    if u in ("people", "persons", "employees", "staff", "workers", "vehicles", "cars", "units"):
        return "count"
    return u or "number"


def decimals(value) -> int:
    """Digits after the decimal point as written. A whole number counts as 0 even when the model
    returns it as a float (97.0 for "about $97 billion")."""
    if isinstance(value, float) and value.is_integer():
        return 0
    s = f"{value}".rstrip("0") if isinstance(value, float) else f"{value}"
    return len(s.split(".")[1]) if "." in s and "e" not in s else 0


def normalize_text_value(text: str) -> str:
    t = re.sub(r"[^a-z0-9 ]", " ", (text or "").lower())
    t = re.sub(r"\b(the|a|an|city of|mr|ms|dr)\b", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def make_text_claim(node_id, agent, entity, attribute, period, text_value, quote, sources):
    if not normalize_text_value(text_value):
        raise ValueError("empty text value")
    return {"node_id": node_id, "agent": agent, "entity": normalize_entity(entity), "entity_display": str(entity),
            "attribute": normalize_attribute(attribute), "period": normalize_period(period),
            "value": None, "text_value": str(text_value), "text_norm": normalize_text_value(text_value),
            "scale": "", "unit": "", "kind": "text", "absolute": None, "precision": None,
            "quote": str(quote or "")[:240], "sources": sources}


def make_claim(node_id, agent, entity, attribute, period, value, scale, unit, quote, sources):
    scale_mult = SCALES.get(str(scale or "").lower().strip(), 1.0)
    length_unit = (unit or "").lower()
    if length_unit in ("km",):
        scale_mult *= 1000
    v = float(value)
    return {"node_id": node_id, "agent": agent, "entity": normalize_entity(entity),
            "entity_display": str(entity), "attribute": normalize_attribute(attribute),
            "period": normalize_period(period), "value": v, "scale": str(scale or ""), "unit": str(unit or ""),
            "kind": unit_kind(unit), "absolute": v * scale_mult,
            # half a unit in the last written digit, in absolute terms ("about $97 billion" -> +/- 0.5 bn)
            "precision": 0.5 * 10 ** (-decimals(value)) * scale_mult,
            "quote": str(quote or "")[:240], "sources": sources}


def _sources_for(quote: str, node_sources: dict) -> list:
    ids = [i for i in dict.fromkeys(cited_ids(quote)) if i in node_sources]
    return [{"id": i, "title": node_sources[i][0], "url": node_sources[i][1]} for i in ids]


def parse_claims_json(raw: str) -> list:
    m = re.search(r"\[.*\]", raw, flags=re.S)
    if not m:
        raise ValueError("no JSON list in claim extraction")
    data = json.loads(m.group(0))
    return [c for c in data if isinstance(c, dict)][:MAX_CLAIMS_PER_NODE]


def chart_claims(node_id: str, agent: str, output: str) -> list:
    m = re.search(r"```vega-lite\s*(.*?)```", output, flags=re.S)
    if not m:
        return []
    try:
        spec = json.loads(m.group(1))
    except ValueError:
        return []
    y_title = spec.get("encoding", {}).get("y", {}).get("title", "")
    unit_part = re.search(r"\(([^)]*)\)\s*$", y_title)
    unit_text = unit_part.group(1) if unit_part else ""
    attribute = re.sub(r"\s*\([^)]*\)\s*$", "", y_title)
    scale = next((w for w in ("trillion", "billion", "million", "thousand") if w in unit_text.lower()), "")
    unit = "USD" if re.search(r"usd|\$|dollar", unit_text, re.I) else ("%" if "%" in unit_text else unit_text)
    claims = []
    for v in spec.get("data", {}).get("values", []):
        cat, series = str(v.get("category", "")), str(v.get("series", ""))
        # a year-like category or series is the period; the other one is the entity
        if normalize_period(cat) and not normalize_period(series):
            entity, period = series, cat
        else:
            entity, period = cat, series
        if not normalize_period(period):
            period = ""
        try:
            claims.append(make_claim(node_id, agent, entity, attribute, period, v["value"], scale, unit,
                                     f"chart: {cat} {series} = {v['value']} {unit_text}".strip(), []))
        except (KeyError, TypeError, ValueError):
            continue
    return claims


async def text_claims(node_id: str, agent: str, output: str) -> list:
    text = normalize_citations(strip_chart_blocks(output))
    node_sources = parse_sources(text)
    body = SOURCE_LINE.sub("", text.split("\n---\n")[0])
    if not CITATION.sub("", body).strip():
        return []
    raw = await run_agent("arbitrator", PROMPT.format(max_claims=MAX_CLAIMS_PER_NODE, text=body[:6000]))
    claims = []
    for c in parse_claims_json(raw):
        sources = _sources_for(str(c.get("quote", "")), node_sources)
        try:
            if c.get("value") is None or c.get("value") == "":
                claims.append(make_text_claim(node_id, agent, c.get("entity"), c.get("attribute"), c.get("period"),
                                              c.get("text_value"), c.get("quote"), sources))
            else:
                claims.append(make_claim(node_id, agent, c.get("entity"), c.get("attribute"), c.get("period"),
                                         c.get("value"), c.get("scale"), c.get("unit"), c.get("quote"), sources))
        except (TypeError, ValueError):
            continue
    # a claim without its own citation inherits the node's sources only if the node cites exactly one
    if len(node_sources) == 1:
        only = [{"id": i, "title": t, "url": u} for i, (t, u) in node_sources.items()]
        for c in claims:
            c["sources"] = c["sources"] or only
    return claims


async def extract_claims(node_id: str, skill: str, agent: str, output: str) -> list:
    if skill in SKIP_SKILLS or not isinstance(output, str) or not output.strip():
        return []
    if skill == "chart":
        return chart_claims(node_id, agent, output)
    return await text_claims(node_id, agent, output)
