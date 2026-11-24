import asyncio
import json
import re
import httpx
import os
from agents.base_agent import run_agent
from datetime import date


MAX_QUERIES = 4
RESULTS_PER_QUERY = 4
MAX_SOURCES = 10
FETCH_TOP = 6
SNIPPET_CHARS = 500
CHUNK_CHARS = 700
CHUNKS_PER_SOURCE = 2
PAGE_TIMEOUT = 12
WIKI_URL = "https://en.wikipedia.org/w/api.php"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; AGORA-research-agent/1.0; university project)"}

STOPWORDS = {"the", "and", "for", "with", "that", "this", "from", "are", "was", "were", "has", "have",
             "its", "their", "about", "into", "than", "then", "also", "task", "context", "previous",
             "agents", "agent", "analysis", "chart", "revenue"}


def parse_queries(raw: str, fallback: str) -> list:
    raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            queries = [str(q).strip() for q in data if str(q).strip()]
            if queries:
                return queries[:MAX_QUERIES]
    except json.JSONDecodeError:
        pass
    return [fallback[:200]]


def keywords(text: str) -> set:
    words = re.findall(r"[a-z0-9$%.]{3,}", text.lower())
    return {w.strip(".") for w in words if w.strip(".") and w not in STOPWORDS}


def split_chunks(text: str, size: int = CHUNK_CHARS) -> list:
    chunks, current = [], ""
    for para in re.split(r"\n\s*\n|\n", text):
        para = para.strip()
        if not para:
            continue
        if len(current) + len(para) + 1 > size and current:
            chunks.append(current)
            current = ""
        current = f"{current} {para}".strip()
    if current:
        chunks.append(current)
    return chunks


def best_chunks(text: str, terms: set, n: int = CHUNKS_PER_SOURCE) -> list:
    scored = []
    for chunk in split_chunks(text):
        overlap = len(terms & keywords(chunk))
        digits = min(len(re.findall(r"\d[\d,.]*", chunk)), 10) * 0.1
        scored.append((overlap + digits, chunk))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for score, c in scored[:n] if score > 0]


def format_sources(sources: list) -> str:
    return "\n".join(
        f"[{i}] {s['title']} ({s['url']})\n    {s['snippet']}" for i, s in enumerate(sources, 1)
    )


def dedupe_sources(batches: list, limit: int = MAX_SOURCES) -> list:
    seen, result = set(), []
    for batch in batches:
        for s in batch:
            if s["url"] and s["url"] not in seen:
                seen.add(s["url"])
                result.append(s)
    return result[:limit]


async def _web_search(query: str) -> list:
    def _search():
        from ddgs import DDGS
        return list(DDGS().text(query, max_results=RESULTS_PER_QUERY))
    try:
        rows = await asyncio.to_thread(_search)
    except Exception as e:
        print(f"[WEB SEARCH ERROR] {query!r}: {type(e).__name__}: {e}")
        return []
    return [{"title": r.get("title", ""), "url": r.get("href", ""),
             "snippet": (r.get("body") or "")[:SNIPPET_CHARS], "type": "web"}
            for r in rows if r.get("href")]


async def _wikipedia(query: str) -> list:
    params = {
        "action": "query", "format": "json", "generator": "search", "gsrsearch": query,
        "gsrlimit": 2, "prop": "extracts|info", "exintro": 1, "explaintext": 1,
        "exchars": 900, "inprop": "url",
    }
    try:
        async with httpx.AsyncClient(timeout=15, headers=HEADERS) as client:
            resp = await client.get(WIKI_URL, params=params)
            resp.raise_for_status()
            pages = resp.json().get("query", {}).get("pages", {})
    except Exception as e:
        print(f"[WIKIPEDIA ERROR] {query!r}: {type(e).__name__}: {e}")
        return []
    ordered = sorted(pages.values(), key=lambda p: p.get("index", 99))
    return [{"title": p["title"] + " (Wikipedia)", "url": p.get("fullurl", ""),
             "snippet": p["extract"][:SNIPPET_CHARS * 2], "type": "wikipedia"}
            for p in ordered if p.get("extract")]


async def _fetch_page_text(url: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=PAGE_TIMEOUT, headers=HEADERS, follow_redirects=True) as client:
            resp = await client.get(url)
        if resp.status_code != 200 or "html" not in resp.headers.get("content-type", "").lower():
            return ""
        html = resp.text[:1_500_000]
    except Exception as e:
        print(f"[PAGE FETCH ERROR] {url}: {type(e).__name__}")
        return ""

    def _extract():
        import trafilatura
        return trafilatura.extract(html) or ""
    try:
        return await asyncio.to_thread(_extract)
    except Exception:
        return ""


async def enrich_sources(sources: list, terms: set) -> list:
    """Download the top web pages and replace each snippet with its most relevant passages."""
    targets = [s for s in sources if s["type"] == "web"][:FETCH_TOP]
    texts = await asyncio.gather(*(_fetch_page_text(s["url"]) for s in targets))
    for source, text in zip(targets, texts):
        if text:
            passages = best_chunks(text, terms)
            if passages:
                source["snippet"] = " ... ".join(passages)
                source["fetched"] = True
    return sources

SEC_CACHE = {}
REVENUE_CONCEPTS = ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"]


def parse_plan(raw: str, fallback: str):
    """Accepts a JSON list of queries or {"queries": [...], "tickers": [...]}."""
    cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return [fallback[:200]], []
    if isinstance(data, list):
        queries, tickers = data, []
    elif isinstance(data, dict):
        queries, tickers = data.get("queries", []), data.get("tickers", [])
    else:
        return [fallback[:200]], []
    queries = [str(q).strip() for q in queries if str(q).strip()][:MAX_QUERIES] or [fallback[:200]]
    tickers = [str(t).strip().upper() for t in tickers if re.fullmatch(r"[A-Za-z.\-]{1,6}", str(t).strip())][:4]
    return queries, tickers


def annual_values(entries: list) -> list:
    """Keep only full-year figures from 10-K filings, newest first: [(end_date, value), ...]."""
    by_end = {}
    for e in entries:
        if e.get("form") not in ("10-K", "10-K/A") or "start" not in e or "end" not in e:
            continue
        try:
            days = (date.fromisoformat(e["end"]) - date.fromisoformat(e["start"])).days
        except ValueError:
            continue
        if days < 340 or days > 380:
            continue
        prev = by_end.get(e["end"])
        if prev is None or e.get("filed", "") >= prev.get("filed", ""):
            by_end[e["end"]] = e
    return sorted(((end, v["val"]) for end, v in by_end.items()), reverse=True)


async def _sec_revenue(ticker: str):
    headers = {"User-Agent": f"AGORA student project {os.getenv('SEC_CONTACT_EMAIL', 'student@example.com')}"}
    try:
        async with httpx.AsyncClient(timeout=20, headers=headers) as client:
            if not SEC_CACHE:
                resp = await client.get("https://www.sec.gov/files/company_tickers.json")
                resp.raise_for_status()
                for row in resp.json().values():
                    SEC_CACHE[row["ticker"].upper()] = (row["cik_str"], row["title"])
            found = SEC_CACHE.get(ticker.upper())
            if not found:
                return None
            cik, title = found
            # Companies switch revenue concepts over the years (Apple moved from "Revenues" to
            # "RevenueFromContract..."), so use the concept with the most recent fiscal year.
            best = None
            for concept in REVENUE_CONCEPTS:
                url = f"https://data.sec.gov/api/xbrl/companyconcept/CIK{int(cik):010d}/us-gaap/{concept}.json"
                resp = await client.get(url)
                if resp.status_code != 200:
                    continue
                rows = annual_values(resp.json().get("units", {}).get("USD", []))
                if len(rows) >= 2 and (best is None or rows[0][0] > best[1][0][0]):
                    best = (url, rows)
            if best:
                url, rows = best
                lines = "; ".join(f"fiscal year ended {end}: ${val / 1e9:.2f} billion" for end, val in rows[:5])
                return {"title": f"SEC EDGAR 10-K data: {title} ({ticker.upper()}) annual revenue",
                        "url": url, "type": "sec",
                        "snippet": f"Official annual revenue from 10-K filings (US GAAP, USD): {lines}."}
    except Exception as e:
        print(f"[SEC ERROR] {ticker}: {type(e).__name__}: {e}")
    return None

def normalize_citations(text: str) -> str:
    return text.replace("【", "[").replace("】", "]")


async def _retrieve(queries: list, terms: set) -> list:
    batches = await asyncio.gather(
        *(_web_search(q) for q in queries),
        *(_wikipedia(q) for q in queries[:2]),
    )
    sources = dedupe_sources(batches)
    if sources:
        sources = await enrich_sources(sources, terms)
        pages = sum(1 for s in sources if s.get("fetched"))
        print(f"[RESEARCH] {len(sources)} sources, {pages} full pages read")
    return sources


async def _answer(task_prompt: str, sources: list, provider: str, model: str) -> str:
    prompt = (
        f"{task_prompt}\n\n"
        f"Use ONLY the numbered sources below. Rules:\n"
        f"- Put the source number like [2] after every factual claim or number.\n"
        f"- Never state a number or fact that is not in the sources. If something is missing, write "
        f"'not found in sources'.\n"
        f"- Cover every part of the task (each company, year and metric asked for).\n"
        f"- Maximum 450 words. Plain markdown, no tables wider than 4 columns.\n"
        f"- Do not write a sources list; it is added automatically.\n\n"
        f"SOURCES:\n{format_sources(sources)}"
    )
    return normalize_citations(await run_agent("research", prompt, provider=provider, model=model))


async def grounded_research(task_prompt: str, provider: str = None, model: str = None) -> str:
    raw = await run_agent(
        "research query planner",
        f"{task_prompt}\n\nReturn ONLY a JSON object with two keys:\n"
        f'"queries": {MAX_QUERIES} short web search queries (maximum 6 words each) covering EVERY part of '
        f'the task (each company, year and metric);\n'
        f'"tickers": US stock tickers of the companies named in the task (for example ["TSLA","F","GM"]), '
        f'or [] if there are none.',
        provider=provider, model=model,
    )
    queries, tickers = parse_plan(raw, task_prompt)
    terms = keywords(task_prompt + " " + " ".join(queries))

    sec_results, web_sources = await asyncio.gather(
        asyncio.gather(*(_sec_revenue(t) for t in tickers)),
        _retrieve(queries, terms),
    )
    sec_sources = [s for s in sec_results if s]
    if sec_sources:
        print(f"[RESEARCH] SEC data for {len(sec_sources)} companies")
    sources = dedupe_sources([sec_sources, web_sources], limit=12)

    if not sources:
        answer = await run_agent("research", task_prompt, provider=provider, model=model)
        return ("NOTE: no live sources could be retrieved. The text below comes from model knowledge "
                "and is UNVERIFIED.\n\n" + answer)

    answer = await _answer(task_prompt, sources, provider, model)

    if "not found in sources" in answer.lower():
        raw2 = await run_agent(
            "research query planner",
            f"{task_prompt}\n\nA first draft answer said some parts were missing:\n{answer[:1500]}\n\n"
            f"Write 3 NEW targeted search queries (maximum 6 words each, include the company name, year and "
            f"metric) for ONLY the missing parts. Return ONLY a JSON list of strings.",
            provider=provider, model=model,
        )
        queries2 = [q for q in parse_plan(raw2, "")[0] if q and q not in queries]
        if queries2:
            extra = await _retrieve(queries2, terms | keywords(" ".join(queries2)))
            if extra:
                sources = dedupe_sources([sec_sources, extra, web_sources], limit=12)
                answer = await _answer(task_prompt, sources, provider, model)

    footer = "\n".join(f"[{i}] {s['title']} - {s['url']}" for i, s in enumerate(sources, 1))
    return f"{answer}\n\n---\nSources\n{footer}"