# Run from the repo root. Docker Desktop must be running and `docker compose up -d` done.
.PHONY: up test bench bench-quick priors reset-reputation

up:
	docker compose up -d --build

test:
	docker compose exec backend pytest -q

# Full AGORA-Bench (8 agents x 5 tasks, LLM judge on); results in backend/bench/results/
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
