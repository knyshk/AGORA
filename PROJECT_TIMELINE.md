# AGORA — Project Timeline & Milestones

**Team:** Vedika Agrawal (2023Btech096), Kanishk Jain (2023Btech040)
**Faculty Guide:** Dr. Deepika Prakash
**Mid-term presentation:** October 8, 2026

## Phase-wise progress

| Phase | Description | Status |
|---|---|---|
| Phase 1 | Core orchestration — Docker/local setup, provider-agnostic LLM config, Planner agent, async DAG executor | ✅ Complete |
| Phase 2 | Reputation & trust layer — MCP-inspired agent registry, Redis-backed scoring, reputation-weighted routing | ✅ Complete |
| Phase 2.5 | Reputation accuracy fix — infra/rate-limit errors no longer wrongly penalize agent scores | ✅ Complete |
| Phase 3 | Conflict detection & arbitration — standalone engine, wired into executor, conflict-injection harness for reliable demos | ✅ Complete |
| Phase 9 (partial) | Frontend — task input, live DAG graph view with dependency edges, node output inspector, conflict display, reputation registry view, hover panels | ✅ Complete (core); collaboration/isolated-mode UI pending |
| Phase 10 | Evaluation — routing accuracy, conflict precision/recall, parallel vs sequential latency, measured against real LLM calls | ✅ Complete |
| Multi-provider fallback | Automatic fallback across Groq → OpenRouter → Gemini on rate limits/errors, specialized agent-per-skill routing | ✅ Complete |
| Phase 4 | Advanced RAG (Corrective RAG, provenance tagging) | ⬜ Not started |
| Phase 5 | Dual-mode collaboration playground (Isolated/Collaborative, live presence, hand-off) | ⬜ Not started |
| Phase 6 | Cost & latency ledger | ⬜ Not started |
| Phase 7 | Checkpointing & replay | ⬜ Not started |
| Phase 8 | Security pass (signed manifest verification, scoped tokens, audit log) | ⬜ Not started |

## Timeline of key events

| Date | Milestone |
|---|---|
| Aug 2026 | Project idea finalized (AGORA); synopsis submitted; faculty guide confirmed (Dr. Deepika Prakash) |
| Sep 24–28, 2026 | Kanishk builds initial backend: Docker setup, single-agent call, FastAPI skeleton, Planner + async executor |
| Sep 28–30, 2026 | Reputation & trust layer added (Redis-backed scoring, multi-candidate routing); conflict detection engine built and wired in |
| Oct 1–3, 2026 | Vedika sets up local dev environment (Docker unavailable on her Windows build, migrated to native Python + Redis); fixed reputation scoring bug (infra errors wrongly penalized) and async execution bug (parallel was secretly sequential) |
| Oct 3, 2026 | Conflict-injection harness and Phase 10 evaluation script built; first verified evaluation numbers produced (3/3 routing, 3/3 conflict recall, 0/3 false positives, 2.68x speedup) |
| Oct 3–6, 2026 | Full frontend built from scratch: task input, visual DAG graph with dependency edges, node inspector, conflict arbitration display, reputation registry view |
| Oct 6–7, 2026 | Multi-provider fallback chain added (Groq → OpenRouter → Gemini), specialized agent-per-skill routing; hover panels and UI polish added; re-verified evaluation numbers (3/3, 3/3, 0/3, 2.76x speedup) |
| Oct 7, 2026 | Documentation completed — README, project timeline, architecture docs |
| Oct 8, 2026 | Mid-term presentation |

## What's demoable right now

- Submit a natural-language task → Planner builds a dependency graph live
- Independent agents run in parallel, dependent agents wait for inputs
- Reputation-weighted routing picks the best-performing agent per skill
- A forced conflict demo reliably shows two agents disagreeing, caught and explained by the arbitration engine
- Automatic provider fallback when a rate limit is hit (visible in logs and still succeeds)
- Full visual interface: live graph, node inspector, conflict display, agent trust scores

## What's explicitly out of scope for the mid-term (roadmap only)

- Full collaboration mode with node-level hand-off
- Checkpointing/replay
- Cost ledger
- Security hardening (signature verification, scoped tokens)
- Advanced RAG techniques
