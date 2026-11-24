"""Reset all graded reputation evidence (priors are kept).
Run inside Docker:  docker compose exec backend python reset_score.py"""
from reputation.scoring import reset_scores

reset_scores()
print("reputation evidence reset; priors kept")
