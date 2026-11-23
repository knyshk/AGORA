import asyncio
import json
import httpx
from agents.base_agent import run_agent

MAX_QUERIES = 3
RESULTS_PER_QUERY = 4
MAX_SOURCES = 10
SNIPPET_CHARS = 500
WIKI_URL = "https://en.wikipedia.org/w/api.php"
HEADERS = {"User-Agent": "AGORA-research-agent/1.0 (university project)"}


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


def format_sources(sources: list) -> str:
    return "\n".join(
        f"[{i}] {s['title']} ({s['url']})\n    {s['snippet']}" for i, s in enumerate(sources, 1)
    )


def dedupe_sources(batches: list) -> list:
    seen, result = set(), []
    for batch in batches:
        for s in batch:
            if s["url"] and s["url"] not in seen:
                seen.add(s["url"])
                result.append(s)
    return result[:MAX_SOURCES]


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


async def grounded_research(task_prompt: str, provider: str = None, model: str = None) -> str:
    raw = await run_agent(
        "research query planner",
        f"{task_prompt}\n\nWrite {MAX_QUERIES} short, specific web search queries that would find the facts "
        f"needed for this task. Return ONLY a JSON list of strings, no other text.",
        provider=provider, model=model,
    )
    queries = parse_queries(raw, task_prompt)

    batches = await asyncio.gather(
        *(_web_search(q) for q in queries),
        *(_wikipedia(q) for q in queries[:2]),
    )
    sources = dedupe_sources(batches)

    if not sources:
        answer = await run_agent("research", task_prompt, provider=provider, model=model)
        return ("NOTE: no live sources could be retrieved. The text below comes from model knowledge "
                "and is UNVERIFIED.\n\n" + answer)

    prompt = (
        f"{task_prompt}\n\n"
        f"Use ONLY the numbered sources below. Rules:\n"
        f"- Put the source number like [2] after every factual claim or number.\n"
        f"- Never state a number or fact that is not in the sources. If something is missing, write "
        f"'not found in sources'.\n"
        f"- Maximum 450 words. Plain markdown, no tables wider than 4 columns.\n"
        f"- Do not write a sources list; it is added automatically.\n\n"
        f"SOURCES:\n{format_sources(sources)}"
    )
    answer = await run_agent("research", prompt, provider=provider, model=model)
    footer = "\n".join(f"[{i}] {s['title']} - {s['url']}" for i, s in enumerate(sources, 1))
    return f"{answer}\n\n---\nSources\n{footer}"