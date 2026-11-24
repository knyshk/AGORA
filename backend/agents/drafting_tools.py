"""Drafting agent with verified inline citations.

Flow:
1. Code parses the numbered source list from the research output ("[n] title - url").
2. The LLM writes a short report using only the research, citing [n] after each claim.
3. Code checks the draft:
   - every [n] must exist in the research source list,
   - every sentence with a figure must carry a citation,
   - every figure must appear in the research text (shared numeric grounding).
4. On a failed check the LLM gets one retry with the exact problems fed back.
   If it still fails, the draft is returned with the problems listed openly (never hidden).
5. Code (not the LLM) appends the sources that were actually cited, keeping the research's
   numbering, so citations always point to real retrieved URLs.
"""
import re

from agents.base_agent import run_agent
from agents.grounding import context_numbers, is_grounded

MAX_ATTEMPTS = 2
MAX_WORDS = 400
SOURCE_LINE = re.compile(r"^\[(\d+)\]\s+(.*)\s+-\s+(\S*)\s*$", re.M)
CITATION = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")
NUMBER = re.compile(r"(\d[\d,]*(?:\.\d+)?)(\s?%)?")
FORM_NAMES = re.compile(r"\b(?:10|8|20)[\-\u2010\u2011]?[KQF]\b")  # "10-K" is a form name, not a figure

PROMPT = """Write a clear, well-structured report for the task below, using ONLY facts from the research context.
Rules:
- After every factual claim, cite the research source number in square brackets, e.g. [2] or [1, 3].
- Write citations ONLY as plain numbers in square brackets, like [2]. No other citation style.
- Every sentence that contains a figure MUST have a citation. Copy figures exactly as the research states them.
- Only use source numbers that appear in the research source list: {ids}.
- If the research does not contain something, say it is not available; never fill gaps from memory.
- No forecasts, analyst projections or percentages unless the research states them.
- At most {max_words} words. Markdown headings and bullet points are fine.
- Do NOT write a sources or references list; it is added automatically.

{task}"""

PROMPT_NO_SOURCES = """Write a clear, well-structured report for the task below using ONLY facts from the context.
Do not add numbers that are not in the context. At most {max_words} words. Do not write a references list.

{task}"""


def normalize_citations(text: str) -> str:
    """Models sometimes cite as 【1】 or [2†L1-L4]; rewrite those to [1] / [2]."""
    text = text.replace("【", "[").replace("】", "]")
    return re.sub(r"\[([^\[\]]*?\u2020[^\[\]]*)\]",
                  lambda m: "[" + ", ".join(re.findall(r"(\d+)\u2020", m.group(1))) + "]", text)


def parse_sources(text: str) -> dict:
    """Numbered sources listed by upstream research: {n: (title, url)}."""
    return {int(n): (title.strip(), url) for n, title, url in SOURCE_LINE.findall(text)}


def cited_ids(text: str) -> list:
    ids = []
    for group in CITATION.findall(text):
        ids += [int(x) for x in re.split(r"\s*,\s*", group)]
    return ids


def is_data_number(token: str, percent: bool = False) -> bool:
    """Figures that need a citation: ignore years and small counting words like '3 companies'.
    Percentages always count."""
    plain = token.replace(",", "")
    try:
        value = float(plain)
    except ValueError:
        return False
    if percent:
        return True
    if "." not in plain and "," not in token and 1900 <= value <= 2100:
        return False
    return "." in plain or value >= 10


def split_sentences(text: str) -> list:
    parts = []
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            parts += [s for s in re.split(r"(?<=[.!?])\s+(?=[A-Z*\-(])", line) if s.strip()]
    return parts


def check_draft(draft: str, sources: dict, context: str) -> dict:
    numbers = context_numbers(context)
    unknown = sorted({i for i in cited_ids(draft) if i not in sources})
    uncited, ungrounded, figures = [], [], 0
    for sentence in split_sentences(draft):
        bare = FORM_NAMES.sub(" ", CITATION.sub(" ", sentence))
        data = [num for num, pct in NUMBER.findall(bare) if is_data_number(num, bool(pct))]
        if not data:
            continue
        figures += len(data)
        if sources and not CITATION.search(sentence):
            uncited.append(sentence.strip()[:160])
        for t in data:
            if not is_grounded(float(t.replace(",", "")), numbers):
                ungrounded.append(t)
    words = len(draft.split())
    return {"unknown_citations": unknown, "uncited_sentences": uncited,
            "ungrounded_numbers": sorted(set(ungrounded)), "figures": figures,
            "too_long": words > MAX_WORDS * 1.25, "words": words}


def problems(report: dict) -> list:
    out = []
    if report["unknown_citations"]:
        out.append(f"citations {report['unknown_citations']} are not in the source list")
    if report["uncited_sentences"]:
        out.append("these sentences contain figures but no citation: "
                   + " | ".join(report["uncited_sentences"][:5]))
    if report["ungrounded_numbers"]:
        out.append(f"these figures do not appear in the research: {report['ungrounded_numbers']}")
    if report["too_long"]:
        out.append(f"the draft has {report['words']} words; the limit is {MAX_WORDS}")
    return out


def remove_unknown_citations(draft: str, sources: dict) -> str:
    def fix(m):
        keep = [x for x in re.split(r"\s*,\s*", m.group(1)) if int(x) in sources]
        return f"[{', '.join(keep)}]" if keep else ""
    return CITATION.sub(fix, draft)


def render(draft: str, sources: dict, report: dict, issues: list) -> str:
    body = remove_unknown_citations(draft.strip(), sources) if sources else CITATION.sub("", draft.strip())
    lines = [body, "", "---"]
    used = sorted({i for i in cited_ids(body) if i in sources})
    if used:
        lines.append("Sources")
        lines += [f"[{i}] {sources[i][0]} - {sources[i][1]}" for i in used]
        lines.append("")
    if not sources:
        lines.append("Citation check: the research step listed no sources, so this draft is uncited.")
    elif not issues:
        lines.append(f"Citation check: passed. {report['figures']} figure(s), all cited and found in the research; "
                     f"{len(used)} source(s) cited.")
    else:
        lines.append("Citation check: NOT fully passed. " + "; ".join(issues) + ".")
    return "\n".join(lines)


async def write_draft(prompt: str, provider: str = None, model: str = None) -> str:
    from agents.chart_tools import strip_chart_blocks  # local import avoids a cycle in tests
    context = strip_chart_blocks(prompt)
    sources = parse_sources(context)

    if not sources:
        draft = normalize_citations(await run_agent(
            "drafting", PROMPT_NO_SOURCES.format(max_words=MAX_WORDS, task=context),
            provider=provider, model=model))
        report = check_draft(draft, sources, context)
        return render(draft, sources, report, problems(report))

    ask = PROMPT.format(ids=sorted(sources), max_words=MAX_WORDS, task=context)
    draft, issues, report = "", [], {}
    for attempt in range(MAX_ATTEMPTS):
        request = ask if attempt == 0 else (
            f"{ask}\n\nYour previous draft was rejected because {'; '.join(issues)}.\n"
            f"Previous draft:\n{draft}\n\nRewrite it fixing every problem.")
        draft = normalize_citations(await run_agent("drafting", request, provider=provider, model=model))
        report = check_draft(draft, sources, context)
        issues = problems(report)
        if not issues:
            break
        print(f"[DRAFTING] attempt {attempt + 1} rejected: {issues}")
    return render(draft, sources, report, issues)
