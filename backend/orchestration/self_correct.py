"""Self-correction: fact-check findings flow back into the draft.

After the fact-check node, every claim it marked unsupported or contradicted (with the evidence it
found) is sent back to the drafting agent, which rewrites the report from the research. The new
draft is fact-checked again. The revision is kept only if the share of supported claims does not
go down; otherwise the original stays and the attempt is recorded. Up to MAX_ROUNDS rounds.
Everything is in the event log, so the original draft and each revision can be inspected.
"""
import os
import re

from agents.chart_tools import strip_chart_blocks
from reputation.quality import fact_check_counts

MAX_ROUNDS = int(os.getenv("SELF_CORRECT_ROUNDS", "1"))
ENABLED = os.getenv("SELF_CORRECT", "1") == "1"
FLAG_WORDS = ("unsupported", "contradicted")

REVISION = """{base}

A fact-checker checked your previous draft against the sources it cites and found these problems:
{problems}

Your previous draft:
<<<
{draft}
>>>

Rewrite the report. For every flagged claim: correct it using the research context, or remove it if the
research does not support it. Keep everything that was not flagged. Keep the same citation rules."""


def flagged_claims(fact_check_output: str) -> list:
    out = []
    for line in fact_check_output.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 4 and cells[0].isdigit():
            verdict = next((w for w in FLAG_WORDS if w in cells[2]), None)
            if verdict:
                out.append({"id": int(cells[0]), "claim": cells[1], "verdict": verdict, "evidence": cells[3]})
    return out


def supported_rate(fact_check_output: str):
    counts = fact_check_counts(fact_check_output or "")
    if not counts:
        return None
    supported, unsupported, contradicted, _ = counts
    judged = supported + unsupported + contradicted
    return round(supported / judged, 3) if judged else None


def _prompt(query: str, node: dict, state: dict) -> str:
    context = "\n".join(f"{d}: {strip_chart_blocks(state[d])}" for d in node["depends_on"])
    return f"Task: {query}\nContext from previous agents:\n{context}" if context else f"Task: {query}"


def targets(plan: list, meta: dict) -> list:
    """(fact_check node, drafting node) pairs where both finished and were written by agents."""
    by_id = {n["id"]: n for n in plan}
    pairs = []
    for n in plan:
        if n["agent"] != "fact_check" or meta.get(n["id"], {}).get("status") != "done":
            continue
        for d in n["depends_on"]:
            dm = meta.get(d, {})
            agent = dm.get("agent") or ""
            if by_id.get(d, {}).get("agent") == "drafting" and dm.get("status") == "done" \
                    and agent not in ("reused", "") and not agent.startswith("human:"):
                pairs.append((n, by_id[d]))
    return pairs


async def self_correct(plan, query, state, meta, emit, call_agent, get_manifest, run_id="adhoc"):
    """call_agent(skill, prompt, manifest, run_id, node_id) -> output (the executor's token-checked call)."""
    if not ENABLED:
        return []
    reports = []
    for fc_node, draft_node in targets(plan, meta):
        fc_id, d_id = fc_node["id"], draft_node["id"]
        original_draft, original_fc = state[d_id], state[fc_id]
        before = supported_rate(original_fc)
        accepted_rounds = 0
        for round_no in range(1, MAX_ROUNDS + 1):
            problems = flagged_claims(state[fc_id])
            if not problems:
                break
            await emit("self_correction_started", {"draft_node": d_id, "fact_check_node": fc_id, "round": round_no,
                                                   "flagged": problems, "supported_rate_before": supported_rate(state[fc_id])})
            listing = "\n".join(f"- [{p['verdict']}] {p['claim']} — evidence: {p['evidence']}" for p in problems)
            try:
                new_draft = await call_agent("drafting", REVISION.format(base=_prompt(query, draft_node, state),
                                                                         problems=listing, draft=state[d_id]),
                                             get_manifest(meta[d_id]["agent"]), run_id, d_id)
                trial = {**state, d_id: new_draft}
                new_fc = await call_agent("fact_check", _prompt(query, fc_node, trial),
                                          get_manifest(meta[fc_id]["agent"]), run_id, fc_id)
            except Exception as e:
                await emit("self_correction_failed", {"draft_node": d_id, "round": round_no, "error": str(e)[:200]})
                break
            old_rate, new_rate = supported_rate(state[fc_id]), supported_rate(new_fc)
            accepted = new_rate is not None and (old_rate is None or new_rate >= old_rate)
            await emit("self_correction_finished", {"draft_node": d_id, "fact_check_node": fc_id, "round": round_no,
                                                    "supported_rate_before": old_rate, "supported_rate_after": new_rate,
                                                    "accepted": accepted})
            if not accepted:
                break
            state[d_id], state[fc_id] = new_draft, new_fc
            accepted_rounds += 1
            await emit("node_revised", {"node_id": d_id, "output": new_draft, "round": round_no})
            await emit("node_revised", {"node_id": fc_id, "output": new_fc, "round": round_no})
        after = supported_rate(state[fc_id])
        if accepted_rounds:
            info = {"rounds": accepted_rounds, "supported_rate_before": before, "supported_rate_after": after,
                    "original_output": original_draft}
            meta[d_id]["revision"] = info
            meta[fc_id]["revision"] = {**info, "original_output": original_fc}
        reports.append({"draft_node": d_id, "fact_check_node": fc_id, "before": before, "after": after,
                        "revised": accepted_rounds > 0})
    return reports
