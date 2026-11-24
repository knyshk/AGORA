"""Catch-up digest: what happened in a session since a member last looked.

Deterministic lines are built from the event log first (always available, never invented);
one LLM call then writes a 2-4 sentence summary of those lines. If the LLM fails, the lines alone
are returned.
"""
from agents.base_agent import run_agent

QUIET = {"claims_extracted", "agent_routed", "reputation_updated", "node_started"}

PROMPT = """You are briefing a teammate who just joined a shared AGORA session.
Summarise what happened in 2-4 short sentences, most important first (conflicts and their decisions,
who took over which node, finished or failed runs). Use ONLY the log below; do not add facts.

Log:
{lines}"""


def event_line(e: dict, queries: dict) -> str | None:
    p, t = e["payload"], e["type"]
    run = f"run '{queries.get(e['run_id'], e['run_id'][:8])}'"
    if t in QUIET:
        return None
    if t == "plan_created":
        return f"{run} was planned with {len(p.get('plan', []))} node(s)"
    if t == "node_finished":
        who = p.get("agent") or "agent"
        return f"{run}: node {p.get('node_id')} ({p.get('skill')}) finished by {who}"
    if t == "node_failed":
        return f"{run}: node {p.get('node_id')} ({p.get('skill')}) failed: {str(p.get('error'))[:80]}"
    if t == "node_skipped":
        return f"{run}: node {p.get('node_id')} was skipped (an upstream node failed)"
    if t == "node_takeover_waiting":
        return f"{run}: {p.get('user', {}).get('name')} took over node {p.get('node_id')} ({p.get('skill')})"
    if t == "node_takeover_released":
        return f"{run}: {p.get('user', {}).get('name')} released node {p.get('node_id')} back to the agents"
    if t == "conflict_found":
        return f"{run}: conflict found on {p.get('label')} — {p.get('suggested_resolution')}"
    if t == "conflict_resolved":
        return f"{run}: a reviewer resolved {p.get('label')} as {p.get('value')}"
    if t == "run_finished":
        return f"{run} finished with status {p.get('status')}"
    return None


def digest_lines(events: list, queries: dict) -> list:
    return [line for line in (event_line(e, queries) for e in events) if line]


async def build_digest(events: list, queries: dict, use_llm: bool = True) -> dict:
    lines = digest_lines(events, queries)
    result = {"event_count": len(events), "lines": lines,
              "latest_event_id": events[-1]["id"] if events else None, "summary": None, "summary_by": None}
    if not lines:
        result["summary"] = "Nothing new since you last looked."
        result["summary_by"] = "code"
        return result
    if use_llm:
        try:
            result["summary"] = (await run_agent("digest", PROMPT.format(lines="\n".join(lines[-60:])))).strip()
            result["summary_by"] = "llm"
        except Exception as e:
            print(f"[DIGEST] LLM summary failed: {type(e).__name__}: {e}")
    if not result["summary"]:
        result["summary"] = f"{len(lines)} update(s) since you last looked; see the list."
        result["summary_by"] = "code"
    return result
