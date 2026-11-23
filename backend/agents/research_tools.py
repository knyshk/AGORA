import asyncio
import json
import re
import httpx
from agents.base_agent import run_agent

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
        f"{task_prompt}\n\nWrite {MAX_QUERIES} short, specific web search queries that would find the facts "
        f"needed for this task. Cover EVERY part of the task (each company, each year, each metric). "
        f"Return ONLY a JSON list of strings, no other text.",
        provider=provider, model=model,
    )
    queries = parse_queries(raw, task_prompt)
    terms = keywords(task_prompt + " " + " ".join(queries))
    sources = await _retrieve(queries, terms)

    if not sources:
        answer = await run_agent("research", task_prompt, provider=provider, model=model)
        return ("NOTE: no live sources could be retrieved. The text below comes from model knowledge "
                "and is UNVERIFIED.\n\n" + answer)

    answer = await _answer(task_prompt, sources, provider, model)

    # Corrective pass: search again only for what is missing
    if "not found in sources" in answer.lower():
        raw2 = await run_agent(
            "research query planner",
            f"{task_prompt}\n\nA first draft answer said some parts were missing:\n{answer[:1500]}\n\n"
            f"Write 3 NEW targeted search queries (different wording, include the company name, year and "
            f"metric, for example 'Tesla 2023 total revenues full year') for ONLY the missing parts. "
            f"Return ONLY a JSON list of strings.",
            provider=provider, model=model,
        )
        queries2 = [q for q in parse_queries(raw2, "") if q and q not in queries]
        if queries2:
            extra = await _retrieve(queries2, terms | keywords(" ".join(queries2)))
            if extra:
                sources = dedupe_sources([extra, sources], limit=12)
                answer = await _answer(task_prompt, sources, provider, model)

    footer = "\n".join(f"[{i}] {s['title']} - {s['url']}" for i, s in enumerate(sources, 1))
    return f"{answer}\n\n---\nSources\n{footer}"