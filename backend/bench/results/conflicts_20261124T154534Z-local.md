# Conflict detection (RQ2) — 20261124T154534Z-local

Labelled pairs: 64 (see bench/conflicts.json). Errors count as 'no conflict'. 95% Wilson intervals.

| Method | n | Precision | Recall | F1 | Accuracy | TP | FP | FN | TN | Errors | Excluded (rate limit) | Mean latency (s) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Structured claims (new) | 64 | 0.926 [0.766, 0.979] | 0.781 [0.612, 0.89] | 0.847 | 0.859 | 25 | 2 | 7 | 30 | 0 | 0 | 15.34 |
| Pairwise LLM (old baseline) | 64 | 1.0 [0.886, 1.0] | 0.938 [0.799, 0.983] | 0.968 | 0.969 | 30 | 0 | 2 | 32 | 1 | 0 | 2.87 |

Correct per category:

| Category | Real conflict? | Structured claims (new) | Pairwise LLM (old baseline) |
|---|---|---|---|
| agreement_text | no | 2/2 | 2/2 |
| date | yes | 2/2 | 2/2 |
| different_entity | no | 4/4 | 4/4 |
| different_metric | no | 4/4 | 4/4 |
| different_period | no | 3/4 | 4/4 |
| different_value | yes | 5/6 | 5/6 |
| digit_swap | yes | 4/4 | 4/4 |
| direction | yes | 1/1 | 1/1 |
| multi_claim | yes | 3/5 | 5/5 |
| non_numeric | yes | 1/4 | 4/4 |
| paraphrase | no | 4/5 | 5/5 |
| percentage | yes | 2/2 | 2/2 |
| rounding | no | 6/6 | 6/6 |
| summary_repeat | no | 1/1 | 1/1 |
| unit_conversion | no | 5/5 | 5/5 |
| unit_error | yes | 3/4 | 4/4 |
| verifier_quote | no | 1/1 | 1/1 |
| wrong_year | yes | 4/4 | 3/4 |
