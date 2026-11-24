"""RQ1 at scale: compare routing strategies in simulation, using the production router.

Why: proving that reputation routing beats baselines needs hundreds of runs per strategy, which free LLM
tiers cannot provide. This simulator replays many tasks with agents whose per-task quality is drawn from
their MEASURED AGORA-Bench scores, and routes with exactly the production code (reputation.scoring.route
with in-memory statistics, same prior strength and decay).

Assumption (stated in the report): an agent's quality on a task ~ Beta(mean * K, (1 - mean) * K) with K = 8,
where mean is its AGORA-Bench mean. Scenarios:
  stationary   agents keep their measured quality
  drift        at step DRIFT_AT the default (first-registered) agent's quality drops to DRIFT_TO
               (e.g. the main provider silently swaps its model)
  cold_start   like stationary, but every agent starts from an uninformed prior (no benchmark)

  docker compose exec backend python -m bench.simulate_routing                 # research skill, 30 seeds
  docker compose exec backend python -m bench.simulate_routing --skill research --steps 600 --seeds 30
"""
import argparse
import json
import math
import random
from datetime import datetime, timezone
from pathlib import Path

from bench.run_bench import RESULTS_DIR, load_records
from reputation.scoring import DECAY, MIN_PRIOR_STRENGTH, MODES, PRIOR_STRENGTH, posterior, route

K = 8
FADING_PRIOR = True   # --fixed-prior reproduces the earlier design for comparison
DRIFT_TO = 0.35
COLD_PRIOR = 0.5
SERIES_EVERY = 10
WINDOW = 25


def measured_means(skill: str, files: list) -> dict:
    scores = {}
    for r in load_records(files):
        if r["skill"] == skill and r["score"] is not None:
            scores.setdefault(r["agent"], []).append(r["score"])
    return {a: min(0.98, max(0.02, sum(v) / len(v))) for a, v in scores.items()}


def draw(mean: float, rng: random.Random) -> float:
    return rng.betavariate(mean * K, (1 - mean) * K)


def ordered(means: dict) -> list:
    """Production order (registry/specs.py): the first agent is the default that fixed routing uses."""
    from registry.specs import AGENT_SPECS
    rank = {s["name"]: i for i, s in enumerate(AGENT_SPECS)}
    return sorted(means, key=lambda a: rank.get(a, len(rank)))


def run_once(strategy, means, priors, steps, drift_at, rng):
    agents = ordered(means)
    ev = {a: {"a": 0.0, "b": 0.0, "n": 0, "q": 0.0, "pw": PRIOR_STRENGTH} for a in agents}
    true = dict(means)
    best = agents[0]   # the drift scenario degrades the default (first-registered) agent
    rewards, picks_best, picks_degraded = [], [], []
    for step in range(steps):
        if drift_at is not None and step == drift_at:
            true[best] = DRIFT_TO
        current_best = max(true, key=true.get)

        def stats(a):
            e = ev[a]
            return posterior(priors[a], e["a"], e["b"], e["n"], e["q"], name=a,
                             prior_weight=e["pw"] if FADING_PRIOR else PRIOR_STRENGTH)

        chosen, _ = route(agents, mode=strategy, rng=rng, stats_fn=stats)
        q = draw(true[chosen], rng)
        e = ev[chosen]
        e["a"], e["b"] = e["a"] * DECAY + q, e["b"] * DECAY + (1 - q)
        e["pw"] = max(MIN_PRIOR_STRENGTH, e["pw"] * DECAY)
        e["n"] += 1
        e["q"] += q
        rewards.append(q)
        picks_best.append(chosen == current_best)
        picks_degraded.append(chosen == best)
    return rewards, picks_best, picks_degraded


def ci95(values):
    n = len(values)
    m = sum(values) / n
    if n < 2:
        return m, None
    sd = math.sqrt(sum((v - m) ** 2 for v in values) / (n - 1))
    return m, 1.96 * sd / math.sqrt(n)


def recovery_steps(picks_degraded, drift_at, window=20, threshold=0.2):
    for i in range(drift_at + window, len(picks_degraded)):
        if sum(picks_degraded[i - window:i]) / window < threshold:
            return i - drift_at
    return None


def simulate(means, bench_priors, steps, seeds, drift_at):
    scenarios = {"stationary": (bench_priors, None), "drift": (bench_priors, drift_at),
                 "cold_start": ({a: COLD_PRIOR for a in means}, None)}
    out = {}
    for name, (priors, drift) in scenarios.items():
        out[name] = {}
        for strategy in MODES:
            per_seed_reward, per_seed_best, recoveries, curves = [], [], [], []
            for seed in range(seeds):
                rewards, best, degraded = run_once(strategy, means, priors, steps, drift, random.Random(seed))
                per_seed_reward.append(sum(rewards) / steps)
                per_seed_best.append(sum(best) / steps)
                curves.append(rewards)
                if drift is not None:
                    recoveries.append(recovery_steps(degraded, drift))
            m, half = ci95(per_seed_reward)
            mb, _ = ci95(per_seed_best)
            curve = []
            for t in range(WINDOW, steps + 1, SERIES_EVERY):
                curve.append({"step": t, "quality": round(sum(sum(c[t - WINDOW:t]) / WINDOW for c in curves) / seeds, 4)})
            rec = [r for r in recoveries if r is not None]
            out[name][strategy] = {
                "mean_quality": round(m, 4), "ci95_half": round(half, 4) if half else None,
                "picks_best_share": round(mb, 3),
                "recovery_steps_mean": round(sum(rec) / len(rec), 1) if rec else None,
                "never_recovered": len(recoveries) - len(rec) if drift is not None else None,
                "curve": curve}
    return out


def report_md(meta, results):
    lines = [f"# Routing simulation (RQ1) — {meta['finished_at']}", "",
             f"Skill: {meta['skill']} · agents and measured means: {meta['means']} · {meta['steps']} tasks × "
             f"{meta['seeds']} seeds per strategy · drift at task {meta['drift_at']} to quality {DRIFT_TO}.",
             "Quality per task ~ Beta(mean·8, (1−mean)·8) around each agent's AGORA-Bench mean. "
             f"Routing uses the production router. Prior: {meta['prior_model']}.", ""]
    for scenario, rows in results.items():
        lines += [f"## {scenario}", "", "| Strategy | Mean quality (95% CI) | Picks of current best | Recovery after drift (tasks) |",
                  "|---|---|---|---|"]
        for strategy, r in sorted(rows.items(), key=lambda kv: -kv[1]["mean_quality"]):
            ci = f" ± {r['ci95_half']}" if r["ci95_half"] else ""
            rec = "—" if r["recovery_steps_mean"] is None and r["never_recovered"] is None else \
                f"{r['recovery_steps_mean']} (never: {r['never_recovered']})"
            lines.append(f"| {strategy} | {r['mean_quality']}{ci} | {round(r['picks_best_share'] * 100)}% | {rec} |")
        lines.append("")
    return "\n".join(lines)


def latest_results(prior_model_prefix: str = "fading"):
    for path in sorted(RESULTS_DIR.glob("routing_sim_*.json"), reverse=True):
        data = json.loads(path.read_text())
        if data["meta"].get("prior_model", "").startswith(prior_model_prefix):
            return {**data, "file": path.name}
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skill", default="research")
    ap.add_argument("--steps", type=int, default=600)
    ap.add_argument("--seeds", type=int, default=30)
    ap.add_argument("--drift-at", type=int, default=200)
    ap.add_argument("--bench", default="", help="comma-separated bench result files (default: all of them)")
    ap.add_argument("--fixed-prior", action="store_true", help="old design: the prior keeps full weight forever")
    args = ap.parse_args()
    global FADING_PRIOR
    FADING_PRIOR = not args.fixed_prior

    files = args.bench.split(",") if args.bench else sorted(p.name for p in RESULTS_DIR.glob("bench_*.json"))
    means = measured_means(args.skill, files)
    if len(means) < 2:
        raise SystemExit(f"need benchmark results for at least two {args.skill} agents")
    priors_file = Path(__file__).parent / "priors.json"
    priors = json.loads(priors_file.read_text()) if priors_file.exists() else {}
    bench_priors = {a: priors.get(a, {}).get("prior", COLD_PRIOR) for a in means}

    results = simulate(means, bench_priors, args.steps, args.seeds, args.drift_at)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    meta = {"finished_at": stamp, "skill": args.skill, "means": {a: round(m, 3) for a, m in means.items()},
            "priors": bench_priors, "steps": args.steps, "seeds": args.seeds, "drift_at": args.drift_at,
            "drift_to": DRIFT_TO, "quality_concentration": K, "bench_files": files,
            "prior_model": "fading (x0.97 per update, floor 2)" if FADING_PRIOR else "fixed weight 10"}
    out = RESULTS_DIR / f"routing_sim_{stamp}.json"
    out.write_text(json.dumps({"meta": meta, "results": results}, indent=1))
    md = report_md(meta, results)
    (RESULTS_DIR / f"routing_sim_{stamp}.md").write_text(md)
    print(md + f"\nSaved {out}")


if __name__ == "__main__":
    main()
