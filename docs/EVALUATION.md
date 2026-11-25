# AGORA evaluation (final phase)

Every number below comes from a script in `backend/bench/` and a saved results file in
`backend/bench/results/` (named next to each result), so it can be checked and reproduced.
Sample sizes are given with every number. Runs that failed because of free-tier rate limits are
**excluded and counted**, never scored as failures of the method. All LLMs used are free tiers or a
local open-weight model, so "cost" is notional.

## Mapping to the synopsis research questions

The synopsis (Aug 2026) lists RQ1–RQ5; the final-phase plan renumbered some of them. Both are answered:

| Synopsis question | Where it is answered |
|---|---|
| RQ1 benchmark-seeded reputation converges to accurate trust faster than usage-only | **Convergence** below (simulation): error 0.05 from the first task vs 0.30, usage-only needs ≈ 95 tasks |
| RQ2 a lightweight classifier detects semantic conflicts with acceptable false positives | RQ2 below (64 labelled pairs, cloud and local) |
| RQ3 parallel execution + adaptive routing reduce latency vs sequential | RQ3 below (1.37×, n = 20 per mode) and the budget governor (economy mode) |
| RQ4 live mid-task human intervention improves quality vs pre/post review | User study (protocol ready); live pause / redirect / reassign implemented |
| RQ5 the catch-up digest reduces time to regain context vs the raw transcript | User study, digest part (protocol ready) |
| (plan) fork vs full re-run | RQ5 in the summary below |

## Summary

| Research question | Result | Sample |
|---|---|---|
| **RQ1** Does reputation routing beat fixed / random routing? | When the default agent degrades, reputation routing keeps quality ≈ 0.97 and switches within ≈ 21–38 tasks; fixed routing drops to 0.56 and never recovers; random 0.68 | 600 tasks × 30 seeds per strategy (simulation with the production router, agent quality drawn from measured bench scores) |
| **RQ2** Does structured arbitration detect conflicts better than a pairwise LLM? | Cloud model: structured F1 0.984 (P 1.00, R 0.97) vs pairwise 0.970 (P 0.94, R 1.00). Local 9B model: pairwise 0.968 vs structured 0.847 (P 0.93) | 64 labelled pairs (32 conflicts, 32 hard negatives) |
| **RQ3** Is parallel execution faster than sequential? | 1.37× (4.78 s vs 6.56 s; median of paired ratios 1.29×), theoretical maximum 2× for this plan | 20 parallel / 20 sequential runs, none excluded |
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

## Convergence of trust (synopsis RQ1)

`routing_sim_20261124T170149Z`: trust error = mean |trust − true quality| over the three research agents,
30 seeds. To avoid a circular test, each seed's true quality differs from the benchmark score by random
benchmark error (sd 0.10); the prior still uses the benchmark score.

| Routing | Prior | Error after 1 / 10 / 25 / 50 / 100 tasks | Tasks until error < 0.10 |
|---|---|---|---|
| Thompson | benchmark-seeded | 0.053 / 0.042 / 0.036 / 0.032 / 0.028 | 1 |
| Thompson | usage only | 0.302 / 0.227 / 0.157 / 0.114 / 0.098 | ≈ 95 (never in 11/30 seeds) |
| greedy | benchmark-seeded | 0.053 / 0.045 / 0.041 / 0.039 / 0.038 | 1 |
| greedy | usage only | 0.298 / 0.234 / 0.199 / 0.179 / 0.178 | never (30/30) |

Benchmark-seeded priors give accurate trust from the first task; usage-only scoring needs about 95 tasks
with Thompson sampling and never converges with greedy routing (it never tries the agents it starts out
wrong about). This is the cold-start problem the synopsis describes, measured.

## RQ2 — conflict detection

64 labelled pairs in `bench/conflicts.json`: digit swaps, wrong year, unit errors, multi-claim texts,
non-numeric facts, dates, increase/decrease, and hard negatives (rounding, unit conversion, paraphrase,
different period/entity/metric, verifier quotes). `bench/eval_conflicts.py`.

| LLM used by both methods | Method | Precision | Recall | F1 | File |
|---|---|---|---|---|---|
| cloud free tiers | structured (new) | 1.000 | 0.969 | **0.984** | `conflicts_20261125T151524Z` (after the rounding fix) |
| cloud free tiers | pairwise LLM (old) | 0.941 | 1.000 | 0.970 | same |
| cloud free tiers (earlier run, before the rounding fix) | structured / pairwise | 0.914 / 0.889 | 1.000 / 1.000 | 0.955 / 0.941 | `conflicts_20261124T112739Z` |
| local qwen3.5 9B | structured (new) | 0.926 | 0.781 | 0.847 | `…154534Z-local` |
| local qwen3.5 9B | pairwise LLM (old) | 1.000 | 0.938 | **0.968** | `…152632Z-local` |

The confirming cloud run after the rounding fix has zero false positives for structured arbitration (it missed one
unit error) against two for the pairwise baseline. Interpretation: structured comparison is exact on
numbers (units, rounding) and explains every conflict field by field, but it depends on the model
extracting claims correctly; a small local model extracts less reliably, so the simpler pairwise check
wins there and is 5× faster. A hybrid (pairwise check as a second opinion when extraction finds nothing)
is a natural next step.

## RQ3 — parallel vs sequential

`bench/eval_runtime.py rq3` (`rq3_20261125T155913Z`): plan research (frozen input) → drafting ∥ chart, agents and provider
(Groq) pinned, modes alternated run by run, arbitration off, 60 s pause between runs.

| Mode | n | Mean (s, 95% CI) | Median (s) |
|---|---|---|---|
| parallel | 20 | 4.78 ± 0.43 | 4.79 |
| sequential | 20 | 6.56 ± 0.76 | 6.27 |

Speedup 1.37× (ratio of means), 1.29× (median of paired ratios); no runs excluded. The maximum possible for two
branches is 2×; the gain is limited by the slower branch (drafting, which may retry once). An earlier attempt with
only 9 / 3 valid runs (`rq3_20261124T162900Z`, 28 excluded by rate limits) had suggested 1.71×; the larger sample
replaces it.
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
1. RQ4 user study (5–8 classmates, [USER_STUDY.md](USER_STUDY.md)).
2. Judge–human agreement: hand-label ~20 judged outputs, then `python -m bench.kappa score …`.
