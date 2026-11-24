"""Runtime evaluations, each reproducible from the saved results file.

  rq3          parallel vs sequential execution of the same plan (cloud: Groq only, no fallback),
               research input frozen, agents pinned, modes alternated run by run
  rq5          fork (re-run one node, reuse the rest) vs full re-run (local model, same plan)
  selfcorrect  supported-claim rate before vs after self-correction on the 10 drafting bench tasks
               (local model; fact-check reads frozen source texts so every run sees identical evidence)

  docker compose exec backend python -m bench.eval_runtime rq3 --runs 20
  docker compose exec backend python -m bench.eval_runtime rq5 --runs 5
  docker compose exec backend python -m bench.eval_runtime selfcorrect --repeats 2

Arbitration is switched off inside these measurements (it would add the same work to both arms);
runs that hit infrastructure errors (rate limits, timeouts) are excluded and counted.
"""
import argparse
import asyncio
import json
import math
import statistics
import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from agents import factcheck_tools
from agents.base_agent import force_provider
from bench.run_bench import RESULTS_DIR, load_tasks
from orchestration import executor

FAILED = ("failed", "skipped")


def ci95(values):
    n = len(values)
    if n == 0:
        return None, None
    m = statistics.mean(values)
    return m, (1.96 * statistics.stdev(values) / math.sqrt(n) if n > 1 else None)


def fmt(m, h, unit=""):
    return "—" if m is None else f"{m:.2f}{unit}" + (f" ± {h:.2f}" if h else "")


def save(name, meta, rows, summary, md):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = RESULTS_DIR / f"{name}_{stamp}.json"
    out.write_text(json.dumps({"meta": meta, "summary": summary, "rows": rows}, indent=1, ensure_ascii=False))
    (RESULTS_DIR / f"{name}_{stamp}.md").write_text(md)
    print(md + f"\nSaved {out}")


def ok(result):
    return all(m["status"] not in FAILED for m in result["node_status"].values())


# ---------------- RQ3: parallel vs sequential ----------------

RQ3_PLAN = [{"id": "n1", "agent": "research", "depends_on": []},
            {"id": "n2", "agent": "drafting", "depends_on": ["n1"]},
            {"id": "n3", "agent": "chart", "depends_on": ["n1"]}]


async def rq3(runs: int, pause: float):
    task = next(t for t in load_tasks() if t["id"] == "D1")
    query = "Write a short report comparing Tesla, Ford and GM revenue in 2022 and 2023 with a chart"
    forced = {"n2": "drafting-v1", "n3": "chart-v1"}
    rows = []
    good = {"parallel": 0, "sequential": 0}
    max_attempts = runs * 6
    with patch.object(executor, "arbitrate", new=AsyncMock(return_value=[])):
        for i in range(max_attempts):
            if min(good.values()) >= runs:
                break   # both modes have `runs` valid measurements
            # alternate; once one mode has enough, only the other one runs
            mode = ("parallel" if i % 2 == 0 else "sequential") if max(good.values()) < runs else \
                min(good, key=good.get)
            force_provider("groq")   # pin the provider: no silent fallback to another model
            started = time.time()
            try:
                result = await executor.execute_plan(RQ3_PLAN, query, initial_state={"n1": task["context"]},
                                                     forced_agents=forced, sequential=(mode == "sequential"))
                wall = round(time.time() - started, 2)
                ok_run = ok(result)
                nodes = {k: v.get("duration_s") for k, v in result["node_status"].items() if k != "n1"}
                err = None if ok_run else "; ".join(str(v.get("error"))[:80] for v in result["node_status"].values() if v.get("error"))
            except Exception as e:
                wall, ok_run, nodes, err = round(time.time() - started, 2), False, {}, f"{type(e).__name__}: {e}"[:200]
            rows.append({"i": i, "mode": mode, "wall_s": wall, "ok": ok_run, "node_s": nodes, "error": err})
            good[mode] += 1 if ok_run else 0
            print(f"[{i + 1}] {mode:10s} {wall:6.2f}s {'ok' if ok_run else 'EXCLUDED ' + str(err)[:80]} "
                  f"(valid: {good['parallel']} parallel, {good['sequential']} sequential)")
            await asyncio.sleep(pause * (2 if not ok_run else 1))   # back off after a rate limit
    par = [r["wall_s"] for r in rows if r["ok"] and r["mode"] == "parallel"]
    seq = [r["wall_s"] for r in rows if r["ok"] and r["mode"] == "sequential"]
    (mp, hp), (ms, hs) = ci95(par), ci95(seq)
    pairs = [s / p for p, s in zip(par, seq) if p]
    summary = {"parallel": {"n": len(par), "mean_s": mp, "ci95_half": hp, "median_s": statistics.median(par) if par else None},
               "sequential": {"n": len(seq), "mean_s": ms, "ci95_half": hs, "median_s": statistics.median(seq) if seq else None},
               "speedup_of_means": round(ms / mp, 3) if mp and ms else None,
               "speedup_median_of_pairs": round(statistics.median(pairs), 3) if pairs else None,
               "excluded": sum(1 for r in rows if not r["ok"])}
    md = "\n".join([
        f"# RQ3 parallel vs sequential — {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC", "",
        "Plan: research (frozen input) → drafting ∥ chart. Agents pinned (drafting-v1, chart-v1), provider pinned to Groq, "
        "modes alternated run by run, arbitration off. Times are wall-clock for the whole plan.", "",
        "| Mode | n | Mean (s, 95% CI) | Median (s) |", "|---|---|---|---|",
        f"| parallel | {len(par)} | {fmt(mp, hp)} | {fmt(summary['parallel']['median_s'], None)} |",
        f"| sequential | {len(seq)} | {fmt(ms, hs)} | {fmt(summary['sequential']['median_s'], None)} |", "",
        f"Speedup (ratio of means): **{summary['speedup_of_means']}×** · median of paired ratios: "
        f"{summary['speedup_median_of_pairs']}× · excluded runs (rate limits etc.): {summary['excluded']}.",
        "With two parallel branches the theoretical maximum is 2×; the gain is limited by the slower branch."])
    save("rq3", {"runs_per_mode": runs, "pause_s": pause, "provider": "groq", "plan": RQ3_PLAN}, rows, summary, md)


# ---------------- RQ5: fork vs full re-run ----------------

RQ5_PLAN = [{"id": "n1", "agent": "research", "depends_on": []},
            {"id": "n2", "agent": "drafting", "depends_on": ["n1"]},
            {"id": "n3", "agent": "chart", "depends_on": ["n1"]}]
RQ5_QUERIES = ["Tesla total revenue in 2022 and 2023, with a chart",
               "Ford total revenue in 2022 and 2023, with a chart",
               "General Motors total revenue in 2022 and 2023, with a chart",
               "Apple total net sales in fiscal 2022 and 2023, with a chart",
               "Microsoft total revenue in fiscal 2022 and 2023, with a chart"]


def _calls(result):
    return (result.get("usage") or {}).get("total", {})


async def rq5(runs: int):
    rows = []
    with patch.object(executor, "arbitrate", new=AsyncMock(return_value=[])):
        for i in range(runs):
            query = RQ5_QUERIES[i % len(RQ5_QUERIES)]
            force_provider("ollama")
            t = time.time()
            full = await executor.execute_plan(RQ5_PLAN, query)
            full_s = round(time.time() - t, 2)
            if not ok(full):
                rows.append({"query": query, "ok": False, "error": "full run failed"})
                print(f"[{i + 1}/{runs}] full run failed, excluded")
                continue
            keep = {k: full["outputs"][k] for k in ("n1", "n2")}
            t = time.time()
            fork = await executor.execute_plan(RQ5_PLAN, query, initial_state=keep,
                                               instructions={"n3": "Use a line chart if the data is a time series."})
            fork_s = round(time.time() - t, 2)
            row = {"query": query, "ok": ok(fork), "full_s": full_s, "fork_s": fork_s,
                   "full_calls": _calls(full).get("llm_calls"), "fork_calls": _calls(fork).get("llm_calls"),
                   "full_tokens": _calls(full).get("tokens_in", 0) + _calls(full).get("tokens_out", 0),
                   "fork_tokens": _calls(fork).get("tokens_in", 0) + _calls(fork).get("tokens_out", 0)}
            rows.append(row)
            print(f"[{i + 1}/{runs}] full {full_s}s ({row['full_calls']} calls) · fork {fork_s}s ({row['fork_calls']} calls)")
    good = [r for r in rows if r["ok"]]
    (mf, hf), (mk, hk) = ci95([r["full_s"] for r in good]), ci95([r["fork_s"] for r in good])
    saved = [1 - r["fork_s"] / r["full_s"] for r in good if r["full_s"]]
    tok_saved = [1 - r["fork_tokens"] / r["full_tokens"] for r in good if r["full_tokens"]]
    summary = {"n": len(good), "full_mean_s": mf, "full_ci95_half": hf, "fork_mean_s": mk, "fork_ci95_half": hk,
               "time_saved_mean": round(statistics.mean(saved), 3) if saved else None,
               "tokens_saved_mean": round(statistics.mean(tok_saved), 3) if tok_saved else None,
               "excluded": len(rows) - len(good)}
    md = "\n".join([
        f"# RQ5 fork vs full re-run — {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC", "",
        "Plan: research → drafting ∥ chart, all on the local model. The fork re-runs only the chart node with a new "
        "instruction and reuses research and draft. Arbitration off.", "",
        "| | n | Mean time (s, 95% CI) |", "|---|---|---|",
        f"| full re-run | {len(good)} | {fmt(mf, hf)} |", f"| fork from checkpoint | {len(good)} | {fmt(mk, hk)} |", "",
        f"Time saved by forking: **{round(summary['time_saved_mean'] * 100) if saved else '—'}%** on average · "
        f"LLM tokens saved: **{round(summary['tokens_saved_mean'] * 100) if tok_saved else '—'}%** · excluded: {summary['excluded']}."])
    save("rq5", {"runs": runs, "provider": "ollama", "plan": RQ5_PLAN}, rows, summary, md)


# ---------------- self-correction effect ----------------

SC_PLAN = [{"id": "n1", "agent": "research", "depends_on": []},
           {"id": "n2", "agent": "drafting", "depends_on": ["n1"]},
           {"id": "n3", "agent": "fact_check", "depends_on": ["n2"]}]


async def selfcorrect(repeats: int):
    tasks = load_tasks()
    frozen = {}
    for t in tasks:
        frozen.update(t.get("source_texts") or {})

    async def frozen_fetch(url):
        return frozen.get(url, "")

    rows = []
    with patch.object(executor, "arbitrate", new=AsyncMock(return_value=[])), \
         patch.object(factcheck_tools, "fetch_source_text", new=frozen_fetch):
        for rep in range(repeats):
            for t in [t for t in tasks if t["skill"] == "drafting"]:
                force_provider("ollama")
                started = time.time()
                result = await executor.execute_plan(SC_PLAN, t["task"], initial_state={"n1": t["context"]})
                report = (result.get("self_correction") or [{}])[0]
                rows.append({"task": t["id"], "repeat": rep, "ok": ok(result), "seconds": round(time.time() - started, 1),
                             "before": report.get("before"), "after": report.get("after"),
                             "revised": report.get("revised", False),
                             "extra_calls": (result.get("usage") or {}).get("self_correction", {}).get("llm_calls", 0)})
                r = rows[-1]
                print(f"[{t['id']} #{rep}] before {r['before']} after {r['after']} revised {r['revised']} ({r['seconds']}s)")
    judged = [r for r in rows if r["ok"] and r["before"] is not None and r["after"] is not None]
    flagged = [r for r in judged if r["before"] < 1.0]
    mb, hb = ci95([r["before"] for r in judged])
    ma, ha = ci95([r["after"] for r in judged])
    fb, _ = ci95([r["before"] for r in flagged])
    fa, _ = ci95([r["after"] for r in flagged])
    summary = {"runs": len(rows), "judged": len(judged), "with_flagged_claims": len(flagged),
               "revised_and_kept": sum(1 for r in rows if r["revised"]),
               "supported_before_mean": mb, "supported_after_mean": ma,
               "flagged_before_mean": fb, "flagged_after_mean": fa,
               "fully_supported_before": sum(1 for r in judged if r["before"] == 1.0),
               "fully_supported_after": sum(1 for r in judged if r["after"] == 1.0)}
    md = "\n".join([
        f"# Self-correction effect — {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC", "",
        f"10 drafting bench tasks × {repeats} repeats on the local model; the fact-checker reads frozen source texts. "
        "A revision is kept only if the share of supported claims does not fall.", "",
        "| | Share of claims supported (mean, 95% CI) | Drafts with every claim supported |", "|---|---|---|",
        f"| before self-correction | {fmt(mb, hb)} | {summary['fully_supported_before']}/{len(judged)} |",
        f"| after self-correction | {fmt(ma, ha)} | {summary['fully_supported_after']}/{len(judged)} |", "",
        f"Drafts with at least one flagged claim: {len(flagged)}/{len(judged)}; among them the supported share went from "
        f"{fmt(fb, None)} to {fmt(fa, None)}. Revisions kept: {summary['revised_and_kept']}."])
    save("selfcorrect", {"repeats": repeats, "provider": "ollama", "plan": SC_PLAN}, rows, summary, md)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("experiment", choices=["rq3", "rq5", "selfcorrect"])
    ap.add_argument("--runs", type=int, default=20)
    ap.add_argument("--pause", type=float, default=20.0)
    ap.add_argument("--repeats", type=int, default=2)
    args = ap.parse_args()
    if args.experiment == "rq3":
        asyncio.run(rq3(args.runs, args.pause))
    elif args.experiment == "rq5":
        asyncio.run(rq5(args.runs))
    else:
        asyncio.run(selfcorrect(args.repeats))


if __name__ == "__main__":
    main()
