# AGORA — Requirements Document

**BTech Major Project (PR1107)**
**Team:** Vedika Agrawal (2023Btech096), Kanishk Jain (2023Btech040)
**Faculty Guide:** Dr. Deepika Prakash

## 1. Problem Statement

- Agent pipelines today run in a fixed, pre-scripted order. There is no standard mechanism for output-driven, asynchronous activation — a fact-checking agent should start the moment a drafting agent's relevant section is ready, not before and not on a fixed delay.
- There is no persistent, meaningful trust score per agent. Routing decisions are hard-coded by the developer rather than informed by track record.
- When two specialized agents touch the same piece of shared work and disagree (e.g. a chart agent using a stale figure a research agent has since corrected), nothing detects it — the error ships silently.
- Multiplayer AI products force one interaction style (shared chat). Users have no way to say "let me work with the agents privately" versus "bring my team into this live session" — the mode is fixed by the product, not chosen by the task.

## 2. Objectives

1. Design a dependency-graph (DAG) based orchestration engine where each agent activates asynchronously based on the readiness of its required inputs, not a fixed sequence.
2. Build a reputation layer seeded with standardized benchmark scores per agent skill category, updated from live outcomes.
3. Build a conflict detection and arbitration engine that flags disagreements between agent outputs on shared resources and proposes a resolution.
4. Register agents through a skill-scoped registry (MCP-inspired) so new agents can plug in without bespoke integration.
5. Add automatic provider fallback so a rate limit or outage on one LLM provider doesn't stop the system.
6. Define measurable evaluation goals for routing accuracy, conflict-detection reliability, and orchestration latency.
7. *(Planned)* Implement a dual-mode playground — Isolated Mode for a single user, Collaborative Mode for a shared live session.

## 3. Functional Requirements

| ID | Requirement |
|---|---|
| FR1 | The system shall accept a natural-language task query from the user |
| FR2 | The system shall decompose the task into a dependency graph of agent nodes at runtime (not hardcoded) |
| FR3 | The system shall execute independent nodes concurrently and dependent nodes only after their inputs are ready |
| FR4 | The system shall maintain a persistent trust score per agent, seeded from a prior and updated from live outcomes |
| FR5 | The system shall route each task node to the best-scoring available agent for that skill |
| FR6 | The system shall detect factual conflicts between agent outputs touching the same claim and explain the conflict in plain language |
| FR7 | The system shall provide a reliable, repeatable way to demonstrate the conflict-detection flow (conflict-injection harness) |
| FR8 | The system shall automatically fall back to an alternate LLM provider if the primary provider is rate-limited or unavailable, without failing the request |
| FR9 | The system shall distinguish infrastructure failures (rate limits, timeouts) from genuine agent output failures when updating reputation scores |
| FR10 | The system shall expose a live view of the task graph, agent outputs, and any detected conflicts through a web interface |
| FR11 | The system shall expose current agent reputation scores through an API and a UI view |

## 4. Non-Functional Requirements

| ID | Requirement |
|---|---|
| NFR1 | The entire stack shall run on free-tier infrastructure (free LLM API tiers, local/free Redis) |
| NFR2 | Agent calls shall time out and fail gracefully rather than hang indefinitely |
| NFR3 | The frontend shall be responsive across common laptop screen widths |
| NFR4 | API keys and secrets shall never be committed to version control |
| NFR5 | The system shall log routing decisions, fallback events, and detected conflicts for auditability during evaluation |

## 5. Scope

### In scope (mid-term and beyond)
- DAG-based orchestration engine with asynchronous, dependency-triggered agent activation
- 4 specialized agents: research, drafting, chart, fact-check, each with multiple provider-backed variants
- Reputation scoring (benchmark-seeded, updated from outcomes) driving task routing
- Conflict detection engine with a conflict-injection test harness
- Multi-provider fallback chain (Groq, OpenRouter, Gemini)
- Full web frontend: task input, visual DAG graph, node output inspector, conflict display, reputation registry

### Planned, not yet built
- Dual-mode playground (Isolated/Collaborative) with live presence and node-level hand-off
- Checkpointing and rollback
- Cost/latency ledger
- Security hardening — signed manifest verification, scoped tokens, audit log
- Advanced RAG techniques (Corrective RAG, provenance tagging)
- Real MCP protocol compliance (current registry is MCP-inspired, not MCP-compliant)

### Explicitly out of scope
- Blockchain-based components
- A fixed/single-provider dependency (the system must support multiple LLM providers)

## 6. Evaluation Criteria

| Metric | Method |
|---|---|
| Routing accuracy | Deliberately degrade one agent's score and confirm the system correctly routes to the better-performing alternative |
| Conflict-detection reliability | Run labeled real-conflict and clean-pair examples; measure recall and false-positive rate |
| Orchestration latency | Time the same task graph forced sequential vs. allowed to parallelize |

Measured results are in `README.md` and produced by `backend/evaluate.py`.
