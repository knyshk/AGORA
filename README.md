# AGORA — A Collaborative Multi-Agent Orchestration Platform

**BTech Major Project (PR1107)** — Institute of Engineering and Technology (IET), JK Lakshmipat University
**Team:** Vedika Agrawal (2023Btech096), Kanishk Jain (2023Btech040)
**Faculty Guide:** Dr. Deepika Prakash

## What is AGORA?

AGORA is a platform where multiple specialized AI agents (research, drafting, chart, fact-check) work together on a task, coordinated by data dependency rather than a fixed schedule. A Planner agent decomposes a user's request into a dependency graph (DAG) at runtime; independent steps run in parallel. Every agent carries a Redis-backed reputation score, seeded from a benchmark and updated from real outcomes, used to route each step to the best-performing registered agent. A conflict-arbitration engine catches factual disagreements between agent outputs and explains them in plain language.

### The four core mechanisms

1. **Dependency-driven orchestration** — agents activate the moment their inputs are ready, not on a timer; independent nodes run concurrently.
2. **Reputation-weighted routing** — a trust score per agent, blended from a benchmark-seeded prior and live success rate, decides who handles each step.
3. **Conflict detection & arbitration** — disagreements between agent outputs on the same fact are caught, explained, and flagged for resolution.
4. **Dual-mode playground** *(planned)* — Isolated Mode for solo work, Collaborative Mode for a shared live session.

## Why this project

Existing multi-agent frameworks (CrewAI, AutoGen, LangGraph) chain agents together but have no way to know which agent is actually reliable, and no mechanism to catch it when two agents produce conflicting outputs. Existing multiplayer AI products (ChatGPT Group Chats, Dust, GitHub Ace) let people work near an AI only as a shared chat thread, never as a shared live view over an evolving multi-agent task. AGORA is designed to close this gap.

## Verified results (Phase 10 evaluation)

| Metric | Result |
|---|---|
| Routing accuracy | 3/3 correct routing decisions |
| Conflict recall | 3/3 real conflicts caught |
| False positive rate | 0/3 |
| Parallel vs sequential latency | 2.76x speedup |

See `backend/evaluate.py` for the measurement script.

## Tech stack

| Layer | Technology |
|---|---|
| Backend API | FastAPI (Python, async) |
| Orchestration | Custom async DAG executor |
| LLM access | langchain-openai, multi-provider (Groq, OpenRouter, Gemini) with automatic fallback |
| Reputation store | Redis |
| Frontend | React + Vite, Framer Motion |
| Agent registry | Custom MCP-inspired skill-scoped registry (not full MCP protocol) |

## Project structure

```
AGORA/
├── backend/
│   ├── main.py                  # FastAPI app & routes
│   ├── config.py                # Provider endpoints, model defaults, fallback chain
│   ├── agents/base_agent.py     # LLM call wrapper with provider fallback
│   ├── orchestration/
│   │   ├── planner.py           # Builds the task DAG at runtime
│   │   ├── executor.py          # Async, dependency-driven execution
│   │   └── conflict_demo.py     # Forced-conflict demo harness
│   ├── registry/registry.py     # Agent registration, skill-scoped lookup
│   ├── reputation/scoring.py    # Redis-backed trust scoring
│   ├── arbitration/engine.py    # Conflict detection between agent outputs
│   └── evaluate.py              # Phase 10 evaluation script
├── frontend/
│   └── src/                     # React UI — task input, DAG graph view,
│                                 # conflict display, reputation registry
├── docs/
│   └── ARCHITECTURE.md
├── PROJECT_TIMELINE.md
└── TEAM_UPDATE.md                # Internal handoff notes between teammates
```

## Setup & running locally

### Prerequisites
- Python 3.11
- Node.js (LTS)
- Redis (native install or Docker)

### Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate          # Windows; source venv/bin/activate on Mac/Linux
pip install -r requirements.txt
pip install langchain-community
pip install "redis==4.6.0"
```

Create `backend/.env`:

```
LLM_PROVIDER=groq
LLM_MODEL=openai/gpt-oss-120b
GROQ_API_KEY=your_key
OPENROUTER_API_KEY=your_key
GEMINI_API_KEY=your_key
FALLBACK_CHAIN=groq,openrouter,gemini
REDIS_URL=redis://localhost:6379
```

Run:

```bash
uvicorn main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Opens at `http://localhost:5173`.

### Verify

- `http://127.0.0.1:8000/health` → `{"status":"ok"}`
- `http://127.0.0.1:8000/reputation/scores` → live agent trust scores
- `http://localhost:5173` → the AGORA UI

## Evaluation

```bash
cd backend
python evaluate.py
```

Measures routing accuracy, conflict detection precision/recall, and parallel vs sequential latency against real LLM calls.

## References

See `docs/ARCHITECTURE.md` for the full reference list and design rationale.
