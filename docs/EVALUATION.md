# AGORA evaluation (final phase)

Every number below comes from a script in `backend/bench/` and a saved results file in
`backend/bench/results/` (named next to each result), so it can be checked and reproduced.
Sample sizes are given with every number. Runs that failed because of free-tier rate limits are
**excluded and counted**, never scored as failures of the method. All LLMs used are free tiers or a
local open-weight model, so "cost" is notional.

## Summary

| Research question | Result | Sample |
|---|---|---|
| **RQ1** Does reputation routing beat fixed / random routing? | When the default agent degrades, reputation routing keeps quality ≈ 0.97 and switches within ≈ 21–38 tasks; fixed routing drops to 0.56 and never recovers; random 0.68 | 600 tasks × 30 seeds per strategy (simulation with the production router, agent quality drawn from measured bench scores) |
| **RQ2** Does structured arbitration detect conflicts better than a pairwise LLM? | Cloud model: structured F1 0.955 (P 0.91, R 1.00) vs pairwise 0.941 (P 0.89, R 1.00). Local 9B model: pairwise 0.968 vs structured 0.847 (P 0.93) | 64 labelled pairs (32 conflicts, 32 hard negatives) |
| **RQ3** Is parallel execution faster than sequential? | 1.71× (ratio of means; median of paired ratios 1.85×), theoretical maximum 2× for this plan | **9 parallel / 3 sequential runs only** (28 excluded by the cloud rate limit); to be repeated |
| **RQ5** Is forking from a checkpoint cheaper than re-running? | 7.4 ± 0.8 s vs 95.2 ± 13.6 s: **92 % less time, 85 % fewer LLM tokens** | 5 pairs, local model |
| **Self-correction** Does feeding fact-check results back improve drafts? | Supported claims 0.72 ± 0.09 → **0.87 ± 0.06**; drafts with every claim supported 4/20 → **9/20** | 10 bench tasks × 2, local model |
| **Tools vs plain LLM** | Grounded research 1.00 vs plain model 0.50 | 10 tasks each (AGORA-Bench) |
| **Local 9B vs cloud 120B** (same tools) | research 1.00 vs 1.00 · chart 0.97 vs 1.00 · drafting 0.88 vs 0.98 · fact-check 0.85 vs 1.00; local research 41 s vs 9 s | 10 tasks per agent |
| **RQ4** Does live collaboration help people? | Not yet run: protocol ready in [USER_STUDY.md](USER_STUDY.md) | 5–8 participants planned |

## AGORA-Bench (agent quality)

40 tasks, 10 per skill, two tiers (core and hard). Research tasks are live (web + SEC); drafting,
chart and fact-check tasks use frozen inputs, so every agent sees identical data. Deterministic
checks first (figures present, citations, units, chart points, verdicts), plus an LLM judge on a
different provider for open-ended quality (cloud runs only).

| Agent | Model | Score (n = 10) |
|---|---|---|
| research-v1 (grounded) | gpt-oss-120b | 1.00 |
| research-v2 (plain, no tools) | gemini flash-lite | 0.50 |
| research-local (grounded) | qwen3.5 9B (laptop) | 1.00 |
| drafting-v1 / v2 / local | 120b / qwen 27b / qwen3.5 9B | 0.98 / 0.98 / 0.88 |
| chart-v1 / v2 / local | 120b / 20b / qwen3.5 9B | 1.00 / 1.00 / 0.97 |
| fact_check-v1 / v2 / local | 120b / gemini / qwen3.5 9B | 1.00 / 1.00 / 0.85 |

Files: `bench_20261124T091935Z-regraded`, `…093456Z`, `…093858Z`, `…094147Z` (cloud), `…143503Z`,
`…143549Z`, `…143841Z`, `…144538Z` (local, deterministic checks only, judge off).
The benchmark found real bugs, which were fixed and re-measured: a grader bug ("unsupported" parsed as
"supported"), charts mixing billions and millions, stale SEC data for Apple, and an unretried JSON error
in fact-checking. Reputation priors are derived from these scores (`bench/priors.json`).

**Limits.** One run per task; LLM outputs vary between runs. Within chart, drafting and fact-check the
cloud agents tie, so the bench alone cannot rank them. The LLM judge was lenient in one observed case;
judge–human agreement (Cohen's kappa, `bench/kappa.py`) still needs hand labels.

## RQ1 — routing (simulation)

`bench/simulate_routing.py` replays 600 tasks × 30 seeds per strategy with exactly the production
router (`reputation.scoring.route`). Each agent's quality on a task is drawn from Beta(8m, 8(1−m)) around
its measured bench mean m (stated assumption). Scenario "drift": at task 200 the default
(first-registered) agent's quality drops to 0.35, like a provider silently swapping its model.

Three research agents (`routing_sim_20261124T144624Z`):

| Strategy | Mean quality (drift scenario) | Tasks to switch after the drop |
|---|---|---|
| greedy (mean trust) | 0.976 | 20.8 |
| Thompson sampling | 0.969 | 22.0 |
| success rate (no decay) | 0.957 | 38.5 |
| random | 0.677 | 128.6 (1/30 seeds never) |
| fixed (default agent) | 0.559 | never (30/30) |

Two-agent hard case (only a weak alternative): the simulation exposed a design flaw. With a
benchmark prior of fixed weight, Thompson took 262 tasks to switch and never switched in 21/30 seeds
(`…141746Z`); with a prior that fades as live evidence accumulates (current design) it takes 175 tasks
and always switches (`…141735Z`). Honest observation: with few agents, greedy switches faster than
Thompson because exploration has little to gain.

**Limits.** Simulation, not live runs (free tiers cannot support hundreds of runs per strategy); latency
is not part of the simulated objective.

## RQ2 — conflict detection

64 labelled pairs in `bench/conflicts.json`: digit swaps, wrong year, unit errors, multi-claim texts,
non-numeric facts, dates, increase/decrease, and hard negatives (rounding, unit conversion, paraphrase,
different period/entity/metric, verifier quotes). `bench/eval_conflicts.py`.

| LLM used by both methods | Method | Precision | Recall | F1 | File |
|---|---|---|---|---|---|
| cloud free tiers | structured (new) | 0.914 | 1.000 | **0.955** | `conflicts_20261124T112739Z` |
| cloud free tiers | pairwise LLM (old) | 0.889 | 1.000 | 0.941 | same |
| local qwen3.5 9B | structured (new) | 0.926 | 0.781 | 0.847 | `…154534Z-local` |
| local qwen3.5 9B | pairwise LLM (old) | 1.000 | 0.938 | **0.968** | `…152632Z-local` |

The cloud run was taken before a rounding fix that removed the cause of its 3 false positives; the
confirming cloud re-run is pending (rate limits). Interpretation: structured comparison is exact on
numbers (units, rounding) and explains every conflict field by field, but it depends on the model
extracting claims correctly; a small local model extracts less reliably, so the simpler pairwise check
wins there and is 5× faster. A hybrid (pairwise check as a second opinion when extraction finds nothing)
is a natural next step.

## RQ3 — parallel vs sequential

`bench/eval_runtime.py rq3`: plan research (frozen input) → drafting ∥ chart, agents and provider (Groq)
pinned, modes alternated run by run, arbitration off.

| Mode | n | Mean (s) | Median (s) |
|---|---|---|---|
| parallel | 9 | 4.11 ± 0.76 | 3.73 |
| sequential | 3 | 7.01 ± 0.73 | 6.90 |

Speedup 1.71× (ratio of means), 1.85× (median of paired ratios); maximum possible for two branches is 2×.
**28 of 40 attempts were excluded by Groq's free-tier limit, so this is indicative only.** A second
attempt with 60 s pauses was stopped after Groq's daily quota ran out. Re-run after the quota resets:
`docker compose exec backend python -m bench.eval_runtime rq3 --runs 20 --pause 60`.
Note: the local model serves one request at a time (measured: 2 parallel calls take 2× as long), so
parallel speedup needs a backend that serves concurrent requests (any cloud API).

## RQ5 — fork vs full re-run

`bench/eval_runtime.py rq5` (`rq5_20261124T164331Z`): plan research → drafting ∥ chart on the local model;
the fork re-runs only the chart node with a new instruction and reuses research and draft.

| | n | Mean time (s) |
|---|---|---|
| full re-run | 5 | 95.2 ± 13.6 |
| fork from checkpoint | 5 | 7.4 ± 0.8 |

92 % less time and 85 % fewer LLM tokens. (Early cloud data point: 21 s vs 51 s, n = 1.)

## Self-correction

`bench/eval_runtime.py selfcorrect` (`selfcorrect_20261124T163457Z`): the 10 drafting bench tasks × 2,
local model; drafting → fact-check (frozen source texts) → self-correction.

| | Claims supported (mean) | Drafts with every claim supported |
|---|---|---|
| before | 0.72 ± 0.09 | 4/20 |
| after | 0.87 ± 0.06 | 9/20 |

16/20 drafts had at least one flagged claim; among them the supported share rose 0.65 → 0.84.
14 revisions were kept (a revision is kept only if the supported share does not fall). Cost: one extra
drafting call and one extra fact-check call per revised draft.

## Still to do
1. RQ3 with ≥ 20 runs per mode (after the cloud quota resets).
2. RQ2 confirming cloud run after the rounding fix.
3. RQ4 user study (5–8 classmates, [USER_STUDY.md](USER_STUDY.md)).
4. Judge–human agreement: hand-label ~20 judged outputs, then `python -m bench.kappa score …`.
