# AGORA — Collaborative Multi-Agent Orchestration with Measured Trust

**BTech Major Project (PR1107)** — Institute of Engineering and Technology, JK Lakshmipat University
**Team:** Vedika Agrawal (2023Btech096), Kanishk Jain (2023Btech040) · **Guide:** Dr. Deepika Prakash

![CI](https://github.com/knyshk/AGORA/actions/workflows/ci.yml/badge.svg)

AGORA turns a request into a **task graph (DAG)** that specialised, tool-using agents execute in parallel.
Each node goes to the agent with the best **measured** reputation, every factual claim is checked,
disagreements between agents are resolved through **source-aware arbitration with a human approval gate**,
and several people can **watch a run live and take over single nodes**. Every state change is an event in an
append-only log, so any run can be replayed, forked from a checkpoint and audited.

## What it does

| Capability | How |
|---|---|
| **Planning** | An LLM planner builds the DAG; the plan is validated (unknown agents, cycles, bad dependencies) with one corrective retry. |
| **Real agents** | *Research*: web + Wikipedia + page reading + official SEC EDGAR XBRL data, answers only from numbered sources, corrective second retrieval pass, source list added by code. *Drafting*: report with inline citations; code rejects unknown citations, uncited figures and figures absent from the research. *Chart*: the LLM only extracts data points; code validates them (JSON Schema, every value grounded in the research, one unit per chart) and builds a Vega-Lite spec. *Fact-check*: re-reads each cited source and labels every claim supported / unsupported / contradicted / unverifiable with a quote. |
| **Measured trust** | One Beta distribution per agent: prior from **AGORA-Bench** (40 tasks, two tiers), updated from graded output quality (each agent's own checks, fact-check feedback, reviewed conflicts); older evidence decays; rate limits never count. Routing by Thompson sampling × a speed term, with a stored explanation for every choice, plus baseline modes (random, fixed, success-rate) for evaluation. |
| **Structured arbitration** | Claims are extracted as (entity, metric, period, value); numbers are compared in code with unit and rounding tolerance; text facts get an LLM entailment check only inside their group. The recommendation ranks sources (SEC > official > Wikipedia > web > uncited) and agent trust. Low-stakes conflicts (an official source against an uncited one) are **auto-resolved** and can be overridden; the rest wait for a person, with an "Auto-apply recommendation" button. A run with open conflicts ends as `needs_review`; the reviewer's decision updates reputation (only the origin of a wrong figure is penalised) and can re-run the losing node with the approved figure. |
| **Persistence, replay, fork** | Postgres event log (Alembic migrations); replay to any event; fork from a checkpoint re-runs one node and its descendants and reuses the rest. |
| **Live collaboration** | Accounts (argon2 + JWT), sessions (isolated → collaborative without losing state), owner/editor/viewer roles, invite links, WebSocket broadcast of the event log, presence, **live token streaming** of every running node, node takeover with locks (a person writes the node instead of an agent), **mid-task control of a single node** (pause, resume, redirect with a new instruction, reassign to another agent) while siblings keep running, catch-up digest. |
| **Security** | Agents served as a real **MCP** server (official SDK); Ed25519-**signed agent manifests** verified at startup (a tampered manifest is rejected); short-lived **task-scoped tokens** for every agent call; **append-only, hash-chained audit log** (UPDATE/DELETE blocked by the database). |
| **Cost and reliability** | Per-node ledger of every LLM call (tokens, latency, notional cost); budget governor (economy mode at 80 %, skip at 100 %); per-node timeout with reassignment. |
| **Observability** | Dashboard computed only from stored events: runs per day, per-agent success/latency/quality/cost, trust over time, conflicts, human decisions, audit-log integrity, and the routing-strategy simulation. |
| **Local LLM (on the laptop)** | An open-weight model (qwen3.5 9B via Ollama) is a provider and the last fallback: when every cloud tier is rate-limited, work continues locally. "Run on my laptop" plans and runs a whole task with no cloud LLM; local agents carry signed manifests and benchmark-derived trust. |
| **Self-correction** | Claims the fact-checker marks unsupported or contradicted go back to the drafting agent with the evidence; the rewrite is fact-checked again and kept only if more claims are supported. The original stays visible. |
| **Shareable report** | One click exports a run as a Word document or a printable page (Save as PDF): the cited report, the chart, sources, fact-check table, conflicts and decisions, and how it was produced (agents, models, quality, tokens, why each agent was chosen, audit-log state). |

## Measured results so far

Full write-up with every number, sample size and result file: [docs/EVALUATION.md](docs/EVALUATION.md).
Headline: forking saves 92 % of time (n = 5); self-correction raises supported claims 0.72 → 0.87
(n = 20); reputation routing keeps quality ≈ 0.97 when the default agent degrades while fixed routing
drops to 0.56 (simulation, 600 × 30); parallel execution 1.71× (indicative, n = 9 / 3).


Every number comes from a script in this repository and a saved results file in `backend/bench/results/`.
Sample sizes are given next to each number. The full evaluation (RQ1–RQ5 with baselines) is in progress.

| Question | Result | Sample | Source |
|---|---|---|---|
| Tool use vs plain LLM (research) | grounded agent 1.00 vs plain model 0.50 mean score | 10 tasks each | AGORA-Bench, `bench/run_bench.py` |
| Agent quality (all skills) | 0.98–1.00 for every tool-using agent | 10 tasks per agent | AGORA-Bench |
| Conflict detection (RQ2) | structured F1 0.955 (precision 0.91, recall 1.00) vs pairwise-LLM baseline F1 0.941 (precision 0.89) | 64 labelled pairs | `bench/eval_conflicts.py` — a rounding bug behind all 3 false positives has been fixed since; a confirming run is pending (free-tier quota) |
| Fork vs full re-run (RQ5) | 21 s vs 51 s | 1 run | early measurement, to be repeated |
| Local 9B model vs cloud 120B (same tools) | research 1.00 vs 1.00 · chart 0.97 vs 1.00 · drafting 0.88 vs 0.98 · fact-check 0.85 vs 1.00; local is slower (research 41 s vs 9 s) | 10 tasks per agent | AGORA-Bench (deterministic checks) |
| Routing when the default agent degrades (RQ1, simulation) | reputation strategies keep quality ≈ 0.97 and switch within ≈ 21–38 tasks; fixed routing drops to 0.56 and never recovers | 600 tasks × 30 seeds | `bench/simulate_routing.py` (production router, agents drawn from measured bench scores) |
| Same, two-agent hard case | the simulation exposed that a fixed-weight benchmark prior slowed recovery (Thompson: 262 tasks, 21/30 seeds never switched); a fading prior fixed it (175 tasks, 0/30) | 600 × 30 | `routing_sim_20261124T141735Z` vs `…141746Z` |
| Conflict detection on the local 9B model | pairwise-LLM baseline F1 0.968 vs structured F1 0.847 (precision 0.93) — structured checking needs a strong extraction model; with the cloud model it wins | 64 labelled pairs | `bench/eval_conflicts.py --local` |

The benchmark also found real bugs (mixed units in charts, stale SEC data for Apple); both were fixed and
re-measured, and the before/after result files are kept.

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the component diagram, the event model and the design decisions.

```
React + Vite UI ──HTTP/WebSocket──► FastAPI ──► planner ─► DAG executor ─► agent gateway (token-checked)
                                       │                         │                 ├─ direct call
                                       │                         │                 └─ MCP server (/agents/mcp)
                                       │                         ├─► structured arbitration
                                       │                         └─► reputation (Redis, Beta)
                                       └─► Postgres: runs · node_runs · run_events · sessions · audit_log
```

## Run it

Needs Docker Desktop (running) and Node 22+. All tools and LLM tiers are free. Optional local model:
`brew install ollama`, `ollama pull qwen3.5:9b` (about 7.6 GB), then
`OLLAMA_CONTEXT_LENGTH=12288 OLLAMA_KEEP_ALIVE=30m ollama serve` before starting AGORA.

```bash
cp backend/.env.example backend/.env      # then fill in your own free API keys (never commit .env)
docker compose up -d --build              # Postgres, Redis, backend on :8000 (migrations run on start)
cd frontend && npm install && npm run dev # UI on http://localhost:5173
```

| Command | What it does |
|---|---|
| `make test` | backend tests inside Docker (no network, LLMs mocked) |
| `cd frontend && npm run test:e2e` | Playwright browser tests (backend mocked) |
| `make bench` / `make priors` | run AGORA-Bench; set reputation priors from it |
| `docker compose exec backend python -m bench.simulate_routing` | routing-strategy simulation (RQ1); `--fixed-prior` reproduces the earlier design |
| `docker compose exec backend python -m bench.eval_conflicts` | conflict-detection evaluation (RQ2) |
| `docker compose exec backend python -m security.sign_manifests` | re-sign agent manifests after editing `registry/specs.py` (needs the private key in `backend/keys/`, which is never committed) |
| `docker compose exec backend alembic revision --autogenerate -m "..."` | new database migration after changing `db/models.py` |

CI (GitHub Actions) runs the backend tests with real Postgres and Redis, the migrations on a fresh database,
the manifest signature check, the frontend lint and build, and the Playwright tests on every push.

## Honest limitations

- The free LLM tiers rate-limit hard; long evaluations must be paced, and some runs fail with HTTP 429.
- Costs are **notional**: the free tiers charge nothing; prices come from an editable assumption table.
- Within chart, drafting and fact-check, the two candidate agents score the same on AGORA-Bench, so the
  bench alone cannot rank them; live quality and speed separate them over time.
- The live hub runs in one backend process; several processes would need Redis pub/sub.
- Text-fact conflict checks depend on one LLM entailment call; numeric checks are deterministic.
- The LLM judge in AGORA-Bench was lenient in one observed case; a hand-labelled agreement check (Cohen's kappa) is prepared (`bench/kappa.py`) but not yet run.

## Repository layout

```
backend/   agents/ (research, drafting, chart, fact-check, usage, MCP client)  orchestration/ (planner, executor, budget, fork)
           arbitration/ (claims, structured, resolution)  reputation/ (Beta scoring, quality grading)  collab/ (sessions, hub, digest)
           security/ (manifests, task tokens, audit)  registry/ (specs, signed manifests, trusted keys)  metrics/  bench/  migrations/  tests/
frontend/  src/components/ (DAG, inspector + conflict review, reputation, run history, live sessions, observability)  e2e/
docs/      ARCHITECTURE.md (current) · REQUIREMENTS.md, PROJECT_TIMELINE.md (mid-term documents, kept for reference)
```
