"""Run AGORA-Bench against the registered agents and (optionally) set reputation priors from it.

Inside Docker:
  docker compose exec backend python -m bench.run_bench                    # all agents, all tasks
  docker compose exec backend python -m bench.run_bench --skill chart      # one skill
  docker compose exec backend python -m bench.run_bench --agent chart-v2 --tasks C1,C3
  docker compose exec backend python -m bench.run_bench --apply-priors     # write bench/priors.json + Redis

Infrastructure errors (rate limits, timeouts) are recorded but NOT scored, and reported separately.
Every reported number is reproducible from the saved results file.
"""
import argparse
import asyncio
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from agents import factcheck_tools
from bench.grader import combine, grade_deterministic, judge
from orchestration.executor import _call_agent, is_infra_error
from registry.registry import REGISTRY
from reputation.scoring import seed_score

HERE = Path(__file__).parent
TASKS_FILE = HERE / "tasks.json"
RESULTS_DIR = HERE / "results"
PRIORS_FILE = HERE / "priors.json"
PRIOR_PSEUDO = 2      # shrink small samples toward 0.5: prior = (sum + 1) / (n + 2)
PRIOR_RANGE = (0.05, 0.95)


def load_tasks(skill=None, ids=None, tier=None):
    tasks = json.loads(TASKS_FILE.read_text())["tasks"]
    return [t for t in tasks if (not skill or t["skill"] == skill) and (not ids or t["id"] in ids)
            and (not tier or t.get("tier", "core") == tier)]


def build_prompt(task):
    if task.get("context"):
        return f"Task: {task['task']}\nContext from previous agents:\nn1: {task['context']}"
    return f"Task: {task['task']}"


async def run_one(task, manifest, use_judge=True):
    frozen = task.get("source_texts") or {}

    async def frozen_fetch(url):
        return frozen.get(url, "")

    started = time.time()
    output, error, infra = None, None, False
    try:
        if frozen:
            with patch.object(factcheck_tools, "fetch_source_text", new=frozen_fetch):
                output = await _call_agent(task["skill"], build_prompt(task), manifest)
        else:
            output = await _call_agent(task["skill"], build_prompt(task), manifest)
    except Exception as e:
        error, infra = f"{type(e).__name__}: {str(e)[:300]}", is_infra_error(e)
    latency = round(time.time() - started, 2)

    deterministic, details = grade_deterministic(task, output) if output else (0.0, {})
    judged = await judge(task, output, manifest.provider) if (use_judge and output) else None
    score = None if infra else (combine(deterministic, judged) if output else 0.0)
    return {"task": task["id"], "skill": task["skill"], "agent": manifest.name, "model": manifest.model,
            "provider": manifest.provider, "strategy": manifest.strategy, "score": score,
            "deterministic": deterministic, "checks": details, "judge": judged, "latency_s": latency,
            "error": error, "infra_error": infra, "output": output}


def summarise(records):
    by_agent = {}
    for r in records:
        by_agent.setdefault(r["agent"], []).append(r)
    summary = {}
    for agent, rows in sorted(by_agent.items()):
        scored = [r["score"] for r in rows if r["score"] is not None]
        n = len(scored)
        mean = sum(scored) / n if n else None
        sd = math.sqrt(sum((s - mean) ** 2 for s in scored) / (n - 1)) if n > 1 else None
        half = 1.96 * sd / math.sqrt(n) if sd is not None else None
        summary[agent] = {
            "skill": rows[0]["skill"], "model": rows[0]["model"], "strategy": rows[0]["strategy"],
            "n_scored": n, "n_infra_errors": sum(1 for r in rows if r["infra_error"]),
            "mean": round(mean, 3) if mean is not None else None,
            "ci95": [round(max(0, mean - half), 3), round(min(1, mean + half), 3)] if half is not None else None,
            "mean_latency_s": round(sum(r["latency_s"] for r in rows) / len(rows), 2),
        }
    return summary


def summary_markdown(summary, meta):
    lines = [f"# AGORA-Bench results ({meta['finished_at']})", "",
             f"Tasks: {meta['n_tasks']} · judge: {'on' if meta['judge'] else 'off'} · "
             "scores in [0, 1]; n = graded runs; infra errors are excluded from scores.", "",
             "| Agent | Skill | Strategy | Model | n | Mean | 95% CI | Infra errors | Mean latency (s) |",
             "|---|---|---|---|---|---|---|---|---|"]
    for agent, s in summary.items():
        ci = f"{s['ci95'][0]}–{s['ci95'][1]}" if s["ci95"] else "—"
        lines.append(f"| {agent} | {s['skill']} | {s['strategy']} | {s['model']} | {s['n_scored']} | "
                     f"{s['mean'] if s['mean'] is not None else '—'} | {ci} | {s['n_infra_errors']} | "
                     f"{s['mean_latency_s']} |")
    return "\n".join(lines) + "\n"


def derive_priors(records):
    priors = {}
    for agent, s in summarise(records).items():
        scored = [r["score"] for r in records if r["agent"] == agent and r["score"] is not None]
        if not scored:
            continue
        p = (sum(scored) + PRIOR_PSEUDO / 2) / (len(scored) + PRIOR_PSEUDO)
        priors[agent] = {"prior": round(min(PRIOR_RANGE[1], max(PRIOR_RANGE[0], p)), 3),
                         "n": len(scored), "bench_mean": s["mean"]}
    return priors


def load_records(files):
    """Records from several results files; later files win for the same (agent, task)."""
    merged = {}
    for f in files:
        path = Path(f) if Path(f).exists() else RESULTS_DIR / f
        for r in json.loads(path.read_text())["records"]:
            merged[(r["agent"], r["task"])] = r
    return list(merged.values())


def apply_priors(records, source_file):
    new = derive_priors(records)
    existing = json.loads(PRIORS_FILE.read_text()) if PRIORS_FILE.exists() else {}
    for agent, p in new.items():
        existing[agent] = {**p, "results_file": source_file}
        seed_score(agent, p["prior"])
    PRIORS_FILE.write_text(json.dumps(existing, indent=1))
    return new


def save(records, meta):
    summary = summarise(records)
    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / f"bench_{meta['finished_at']}.json"
    out.write_text(json.dumps({"meta": meta, "summary": summary, "records": records}, indent=1, ensure_ascii=False))
    md = summary_markdown(summary, meta)
    (RESULTS_DIR / f"bench_{meta['finished_at']}.md").write_text(md)
    print("\n" + md + f"\nSaved {out}")
    return out


def regrade(path, set_priors):
    """Apply the current deterministic checks to stored outputs; judge scores are kept as they were."""
    data = json.loads(Path(path).read_text())
    tasks = {t["id"]: t for t in load_tasks()}
    for r in data["records"]:
        if r["output"] and not r["infra_error"]:
            r["deterministic"], r["checks"] = grade_deterministic(tasks[r["task"]], r["output"])
            r["score"] = combine(r["deterministic"], r.get("judge"))
    meta = {**data["meta"], "regraded_from": Path(path).name,
            "finished_at": data["meta"]["finished_at"] + "-regraded"}
    out = save(data["records"], meta)
    if set_priors:
        for agent, p in apply_priors(data["records"], out.name).items():
            print(f"prior {agent}: {p['prior']} (bench mean {p['bench_mean']}, n={p['n']})")


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skill")
    ap.add_argument("--agent")
    ap.add_argument("--tasks", help="comma-separated task ids")
    ap.add_argument("--no-judge", action="store_true")
    ap.add_argument("--sleep", type=float, default=6.0, help="seconds between calls (free-tier rate limits)")
    ap.add_argument("--apply-priors", action="store_true")
    ap.add_argument("--regrade", help="re-grade the saved outputs of a results file (no agent calls)")
    ap.add_argument("--tier", choices=["core", "hard"])
    ap.add_argument("--priors-from", help="comma-separated results files: set priors from all of them, run nothing")
    args = ap.parse_args()
    if args.regrade:
        return regrade(args.regrade, args.apply_priors)
    if args.priors_from:
        files = args.priors_from.split(",")
        records = load_records(files)
        print(summary_markdown(summarise(records), {"finished_at": "combined: " + ", ".join(files),
                                                    "n_tasks": len({r["task"] for r in records}), "judge": True}))
        for agent, p in apply_priors(records, ",".join(files)).items():
            print(f"prior {agent}: {p['prior']} (bench mean {p['bench_mean']}, n={p['n']})")
        return

    ids = set(args.tasks.split(",")) if args.tasks else None
    tasks = load_tasks(args.skill, ids, args.tier)
    agents = [m for m in REGISTRY.values()
              if (not args.agent or m.name == args.agent) and any(t["skill"] == m.skill for t in tasks)]
    jobs = [(t, m) for m in agents for t in tasks if t["skill"] == m.skill]
    print(f"AGORA-Bench: {len(jobs)} runs ({len(agents)} agents, {len(tasks)} tasks)")

    records = []
    for i, (task, manifest) in enumerate(jobs, 1):
        rec = await run_one(task, manifest, use_judge=not args.no_judge)
        records.append(rec)
        flag = "INFRA" if rec["infra_error"] else (f"{rec['score']:.2f}" if rec["score"] is not None else "-")
        print(f"[{i}/{len(jobs)}] {manifest.name:15s} {task['id']:3s} score={flag} ({rec['latency_s']}s)"
              + (f" error={rec['error'][:80]}" if rec["error"] else ""))
        if i < len(jobs):
            await asyncio.sleep(args.sleep)

    finished = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    meta = {"finished_at": finished, "n_tasks": len(tasks), "judge": not args.no_judge,
            "filters": {"skill": args.skill, "agent": args.agent, "tasks": args.tasks, "tier": args.tier}}
    out = save(records, meta)

    if args.apply_priors:
        for agent, p in apply_priors(records, out.name).items():
            print(f"prior {agent}: {p['prior']} (bench mean {p['bench_mean']}, n={p['n']})")


if __name__ == "__main__":
    asyncio.run(main())
