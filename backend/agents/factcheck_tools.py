"""Fact-check agent: verifies each cited claim against the source it cites.

Flow:
1. Claims = sentences in the upstream text that carry a citation [n] (deterministic, no LLM).
2. Code re-reads every cited source itself (web page text, or the SEC XBRL API for SEC sources),
   so the check is against the real source, not against the research agent's summary.
3. Code picks the best evidence passage per claim and checks every figure in the claim
   against the cited source text (shared numeric grounding).
4. ONE batched LLM call judges each claim: supported / unsupported / contradicted, with a quote.
5. Code combines both: the LLM can never mark a claim "supported" if its figures are not in the
   cited source, and a source that could not be read gives "unverifiable", not a guess.
"""
import asyncio
import json
import os
import re

import httpx

from agents.base_agent import run_agent
from agents.chart_tools import strip_chart_blocks
from agents.drafting_tools import (CITATION, FORM_NAMES, NUMBER, SOURCE_LINE, cited_ids,
                                   is_data_number, normalize_citations, parse_sources, split_sentences)
from agents.grounding import context_numbers, is_grounded
from agents.research_tools import _fetch_page_text, annual_values, best_chunks, keywords

MAX_CLAIMS = 10
MAX_SOURCES_PER_CLAIM = 2
EVIDENCE_CHARS = 500
VERDICTS = ("supported", "unsupported", "contradicted")
ICONS = {"supported": "✅ supported", "unsupported": "⚠️ unsupported",
         "contradicted": "❌ contradicted", "unverifiable": "❔ unverifiable"}

PROMPT = """You are a strict fact-checker. For each claim, decide using ONLY the evidence given for that claim:
- "supported": the evidence states the claim (allow rounding and unit changes such as million -> billion).
- "contradicted": the evidence states something different (e.g. a different number for the same thing).
- "unsupported": the evidence does not mention it.
Quote the exact words from the evidence that decided it (max 25 words, "" if none).

{claims}

Return ONLY a JSON list, no markdown:
[{{"id": 1, "verdict": "supported", "quote": "...", "note": "short reason"}}]"""


def extract_claims(text: str) -> list:
    """Cited sentences, excluding source-list lines and the drafting agent's check line."""
    claims, seen = [], set()
    text = SOURCE_LINE.sub("", text)  # source-list lines are not claims
    text = re.sub(r"```.*?```", " ", text, flags=re.S)  # nor code blocks / text drawings
    for sentence in split_sentences(text):
        if sentence.startswith(("Citation check", "Task:")):
            continue
        ids = [i for i in dict.fromkeys(cited_ids(sentence))]
        if not ids:
            continue
        clean = re.sub(r"^n\d+:\s*", "", sentence).strip(" |-*")
        clean = re.sub(r"\s*\|\s*", "; ", clean).replace("**", "")
        if clean in seen:
            continue
        seen.add(clean)
        claims.append({"id": len(claims) + 1, "text": clean, "sources": ids[:MAX_SOURCES_PER_CLAIM]})
        if len(claims) == MAX_CLAIMS:
            break
    return claims


def claim_figures(claim: str) -> list:
    bare = FORM_NAMES.sub(" ", CITATION.sub(" ", claim))
    return [num for num, pct in NUMBER.findall(bare) if is_data_number(num, bool(pct))]


async def _sec_text(url: str) -> str:
    headers = {"User-Agent": f"AGORA student project {os.getenv('SEC_CONTACT_EMAIL', 'student@example.com')}"}
    try:
        async with httpx.AsyncClient(timeout=20, headers=headers) as client:
            resp = await client.get(url)
        resp.raise_for_status()
        rows = annual_values(resp.json().get("units", {}).get("USD", []))
    except Exception as e:
        print(f"[FACT CHECK] SEC fetch failed {url}: {type(e).__name__}")
        return ""
    return "Official annual revenue from 10-K filings: " + "; ".join(
        f"fiscal year ended {end}: ${val / 1e9:.2f} billion ({val} USD)" for end, val in rows[:8])


async def fetch_source_text(url: str) -> str:
    if not url:
        return ""
    if "data.sec.gov/api/xbrl" in url:
        return await _sec_text(url)
    return await _fetch_page_text(url)


def evidence_for(claim: dict, texts: dict) -> str:
    terms = keywords(claim["text"])
    parts = []
    for sid in claim["sources"]:
        text = texts.get(sid) or ""
        if not text:
            continue
        chunk = (best_chunks(text, terms, n=1) or [text[:EVIDENCE_CHARS]])[0][:EVIDENCE_CHARS]
        parts.append(f"[{sid}] {chunk}")
    return "\n".join(parts)


def figures_check(claim: dict, texts: dict) -> list:
    """Figures in the claim that do NOT appear in any of its cited sources."""
    numbers = context_numbers(" ".join(texts.get(s) or "" for s in claim["sources"]))
    return [f for f in claim_figures(claim["text"]) if not is_grounded(float(f.replace(",", "")), numbers)]


def parse_verdicts(raw: str) -> dict:
    match = re.search(r"\[.*\]", raw, flags=re.S)
    if not match:
        raise ValueError("fact-check model returned no JSON list")
    out = {}
    for row in json.loads(match.group(0)):
        if isinstance(row, dict) and row.get("verdict") in VERDICTS:
            out[int(row.get("id", 0))] = row
    return out


def combine(claim: dict, evidence: str, missing: list, llm: dict | None) -> dict:
    if not evidence:
        return {"verdict": "unverifiable", "quote": "", "note": "cited source could not be read"}
    if llm is None:
        return {"verdict": "unverifiable", "quote": "", "note": "no verdict returned"}
    result = {"verdict": llm["verdict"], "quote": str(llm.get("quote", ""))[:200],
              "note": str(llm.get("note", ""))[:200]}
    if result["verdict"] == "supported" and missing:
        result = {"verdict": "unsupported", "quote": result["quote"],
                  "note": f"figure(s) {', '.join(missing)} not found in cited source"}
    return result


def render(claims: list, results: dict, sources: dict) -> str:
    counts = {v: sum(1 for r in results.values() if r["verdict"] == v) for v in ICONS}
    head = (f"**Fact check: {len(claims)} cited claim(s)** — {counts['supported']} supported, "
            f"{counts['unsupported']} unsupported, {counts['contradicted']} contradicted, "
            f"{counts['unverifiable']} unverifiable. Each claim was checked against the source it cites.")
    lines = [head, "", "| # | Claim | Verdict | Evidence |", "|---|---|---|---|"]
    for c in claims:
        r = results[c["id"]]
        cite = ", ".join(f"[{s}]" for s in c["sources"])
        evidence = f'"{r["quote"]}" {cite}' if r["quote"] else cite
        if r["note"]:
            evidence += f" — {r['note']}"
        lines.append(f"| {c['id']} | {c['text'].replace('|', '/')} | {ICONS[r['verdict']]} | "
                     f"{evidence.replace('|', '/')} |")
    flagged = [c for c in claims if results[c["id"]]["verdict"] in ("unsupported", "contradicted")]
    if flagged:
        lines += ["", "Claims needing attention: " + ", ".join(f"#{c['id']}" for c in flagged) + "."]
    return "\n".join(lines)


async def fact_check(prompt: str, provider: str = None, model: str = None) -> str:
    context = normalize_citations(strip_chart_blocks(prompt))
    sources = parse_sources(context)
    claims = extract_claims(context)
    if not claims or not sources:
        return ("**Fact check:** no cited claims were found in the upstream output, so nothing could be "
                "verified against sources.")

    wanted = sorted({s for c in claims for s in c["sources"] if s in sources})
    fetched = await asyncio.gather(*(fetch_source_text(sources[s][1]) for s in wanted))
    texts = dict(zip(wanted, fetched))
    print(f"[FACT CHECK] {len(claims)} claims, read {sum(1 for t in fetched if t)}/{len(wanted)} sources")

    evidence = {c["id"]: evidence_for(c, texts) for c in claims}
    missing = {c["id"]: figures_check(c, texts) for c in claims}
    to_judge = [c for c in claims if evidence[c["id"]]]

    verdicts = {}
    if to_judge:
        block = "\n\n".join(f"Claim {c['id']}: {c['text']}\nEvidence:\n{evidence[c['id']]}" for c in to_judge)
        raw = await run_agent("fact_check", PROMPT.format(claims=block), provider=provider, model=model)
        verdicts = parse_verdicts(raw)

    results = {c["id"]: combine(c, evidence[c["id"]], missing[c["id"]], verdicts.get(c["id"])) for c in claims}
    return render(claims, results, sources)
