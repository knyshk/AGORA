# AGORA — System Design & Architecture

**BTech Major Project (PR1107)**
**Team:** Vedika Agrawal (2023Btech096), Kanishk Jain (2023Btech040)
**Faculty Guide:** Dr. Deepika Prakash

## 1. High-Level Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     CLIENT INTERFACE                     │
│         React + Vite frontend (localhost:5173)           │
│   Task input · Live DAG graph · Node inspector ·          │
│   Conflict display · Reputation registry                  │
└───────────────────────┬─────────────────────────────────┘
                         │ HTTP (CORS-enabled)
┌───────────────────────▼─────────────────────────────────┐
│                      API GATEWAY                          │
│              FastAPI backend (localhost:8000)             │
└───────────────────────┬─────────────────────────────────┘
                         │
┌───────────────────────▼─────────────────────────────────┐
│                  PLANNER / SUPERVISOR                      │
│   Decomposes the user's query into a dependency graph      │
│   (DAG) at runtime via an LLM call                         │
└───────────────────────┬─────────────────────────────────┘
                         │
          ┌──────────────┼──────────────┬──────────────┐
          ▼              ▼              ▼              ▼
┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│ORCHESTRATION│ │ REPUTATION  │ │ ARBITRATION │ │  REGISTRY   │
│  Async DAG  │ │   Redis-    │ │  Conflict   │ │ Skill-scoped│
│  executor   │ │   backed    │ │  detection  │ │   agent     │
│             │ │   scoring   │ │             │ │   lookup    │
└──────┬──────┘ └─────────────┘ └─────────────┘ └─────────────┘
       │
┌──────▼──────────────────────────────────────────────────┐
│                   SPECIALIZED AGENTS                       │
│  Research · Drafting · Chart · Fact-Check                  │
│  Each with multiple provider-backed variants (v1, v2)      │
└──────┬──────────────────────────────────────────────────┘
       │
┌──────▼──────────────────────────────────────────────────┐
│               LLM PROVIDER FALLBACK CHAIN                  │
│        Groq → OpenRouter → Gemini (auto-retry on           │
│        rate limit / error, skips providers with no key)    │
└─────────────────────────────────────────────────────────┘
```

## 2. Orchestration Flow — Dependency-Driven, Asynchronous Activation

Each agent declares the inputs it needs and the output it produces. The orchestrator builds a directed acyclic graph (DAG) of the task at runtime: an edge from Agent A to Agent B means B needs A's output. B activates only once A's output is marked ready — this is event-driven activation, not a fixed sequence.

**Example** — "Build a competitor analysis report with a chart":
- **Research** starts immediately (no dependency)
- **Drafting** and **Chart** both depend only on Research, so they run *in parallel* the moment Research finishes
- **Fact-Check** depends on both Drafting and Chart, so it waits for whichever finishes last

Implementation: `backend/orchestration/executor.py`. The executor repeatedly scans the remaining nodes for any whose dependencies are now satisfied, and dispatches all of them concurrently via `asyncio.gather`.

A real bug was found and fixed here during development: the underlying LLM call originally used a *synchronous* `invoke()` inside an `async def`, which silently serialized all "parallel" execution despite `asyncio.gather`. This was caught by the Phase 10 latency benchmark (which initially showed parallel execution running *slower* than sequential) and fixed by switching to `ainvoke()` throughout. Measured result after the fix: 2.76x speedup.

## 3. Reputation & Trust Layer

Each agent is registered with a prior trust score (`backend/registry/registry.py`). Live task outcomes update this score in Redis (`backend/reputation/scoring.py`) using a blend of the seeded prior and the live success rate, weighted by how many real outcomes have accumulated:

```
score = (1 - weight) × prior + weight × (successes / total)
weight = min(total / 20, 1.0)
```

When a skill is needed, `pick_best_agent()` selects the highest-scoring registered agent for that skill. This was verified empirically: deliberately tanking one agent's score causes the system to correctly route to its better-performing sibling, 3/3 trials.

**Reputation accuracy fix:** reputation scoring originally penalized *any* exception, including transient infrastructure errors (rate limits, timeouts). This meant a rate-limited agent could look unreliable even though its actual output quality was fine. Fixed by classifying exceptions — only genuine model-output failures now affect the score; infrastructure errors are logged separately and skipped.

## 4. Conflict Detection & Arbitration

After a task graph finishes executing, the arbitration engine (`backend/arbitration/engine.py`) compares pairs of sibling outputs for factual contradictions (conflicting numbers, dates, or claims) using an LLM-based comparison, and returns a plain-language explanation plus a suggested resolution when a conflict is found.

Because real conflicts are rare and timing-dependent in practice, a **conflict-injection harness** (`backend/orchestration/conflict_demo.py`) forces two agents to state deliberately contradicting figures, giving a reliable, repeatable demonstration via the `/tasks/conflict-demo` endpoint — rather than relying on one occurring naturally during a live demo.

## 5. Multi-Provider Fallback

Free-tier LLM APIs have tight rate limits (e.g. Groq: ~8000 tokens/minute). To keep the system usable under load, `backend/agents/base_agent.py` tries providers in a configured order (`FALLBACK_CHAIN` in `.env`) — if the primary provider rate-limits or errors, it automatically retries on the next provider before giving up. This was verified live: a Groq rate limit during testing correctly triggered a fallback to OpenRouter, which completed the request successfully.

Each skill also has a preferred provider/model assignment (`SKILL_PREFERRED_PROVIDER` in `base_agent.py`, and per-agent provider/model in `registry.py`), so, for example, research and drafting default to a larger model while chart and fact-check can use faster ones.

## 6. Frontend

React + Vite application (`frontend/src/`). Key pieces:
- **Task input** — submits a query to `/tasks/run`
- **AgentGraph** — renders the returned plan as a true node-link graph, computing node positions by dependency depth and drawing connecting SVG edges between dependent nodes; nodes are colored by conflict status; hovering a node shows a floating panel (rendered via a React portal to avoid clipping) with the agent's role, dependencies, and an output preview
- **InspectorAndConflicts** — shows the full output for a selected node and all detected conflicts with their explanations and suggested resolutions
- **ReputationRegistry** — pulls live trust scores from `/reputation/scores` and displays them per agent

## 7. Security Notes (Current State — Honest Disclosure)

- The agent registry is **MCP-inspired**, not MCP-protocol-compliant: it mimics skill-scoped registration with a manifest, but has no real MCP server/client and no signature verification path. This is a known, intentional scope limitation for the current build, named honestly here rather than overstated.
- `.env` (API keys) is excluded from version control via `.gitignore` and was never committed.

## 8. Known Limitations / Future Work

- No checkpointing/replay — a failed task cannot currently be resumed from a partial state
- No cost/latency ledger surfaced to the end user
- No collaborative/multi-user mode yet (Isolated Mode only)
- Agent manifest signatures are computed but not cryptographically verified anywhere in the call path

## 9. References

1. Qingyun Wu et al., "AutoGen: Enabling Next-Gen LLM Applications via Multi-Agent Conversation," arXiv:2308.08155, 2023.
2. Sirui Hong et al., "MetaGPT: Meta Programming for a Multi-Agent Collaborative Framework," arXiv:2308.00352, 2023.
3. Guohao Li et al., "CAMEL: Communicative Agents for 'Mind' Exploration of Large Language Model Society," arXiv:2303.17760, 2023.
4. Marc Shapiro et al., "Conflict-Free Replicated Data Types," INRIA Research Report RR-7687, 2011.
5. Sepandar D. Kamvar, Mario T. Schlosser, Hector Garcia-Molina, "The EigenTrust Algorithm for Reputation Management in P2P Networks," Proceedings of WWW 2003.
6. Anthropic, "Model Context Protocol Specification," 2024–2026. https://modelcontextprotocol.io
7. LangChain, "LangGraph Documentation," 2026. https://langchain-ai.github.io/langgraph/
8. OpenAI, "Introducing Group Chats in ChatGPT," November 2025.
9. Dust, "Multiplayer Agents for the Enterprise," Dust Product Documentation, 2026. https://dust.tt
10. Liveblocks, "Real-Time Infrastructure for Human and AI Collaboration," 2026. https://liveblocks.io
