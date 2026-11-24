# Run from the repo root. Docker Desktop must be running and `docker compose up -d` done.
.PHONY: up test e2e bench bench-quick priors reset-reputation conflicts

up:
	docker compose up -d --build

test:
	docker compose exec backend pytest -q

# Browser tests (backend mocked); needs `npx playwright install chromium` once
e2e:
	cd frontend && npm run test:e2e

# Conflict-detection evaluation (RQ2): structured arbitration vs pairwise-LLM baseline on 64 labelled pairs
conflicts:
	docker compose exec backend python -m bench.eval_conflicts

# Full AGORA-Bench (40 tasks: 8 agents x 10 tasks of their skill, LLM judge on); results in backend/bench/results/
bench:
	docker compose exec backend python -m bench.run_bench --sleep 8

# Same, and set each agent's reputation prior from the measured scores (backend/bench/priors.json)
priors:
	docker compose exec backend python -m bench.run_bench --sleep 8 --apply-priors

# Deterministic checks only (no judge), one skill: make bench-quick SKILL=chart
bench-quick:
	docker compose exec backend python -m bench.run_bench --no-judge --skill $(SKILL)

reset-reputation:
	docker compose exec backend python reset_score.py
