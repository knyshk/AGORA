"""Judge vs human agreement (Cohen's kappa) for the LLM judge.

1. Export judged outputs to a CSV for hand-labelling:
     docker compose exec backend python -m bench.kappa export bench/results/bench_XXXX.json
   -> bench/results/labels_XXXX.csv  (fill the `human_pass` column with 1 or 0)
2. Compute agreement:
     docker compose exec backend python -m bench.kappa score bench/results/labels_XXXX.csv
A judge score >= PASS (0.5, i.e. 3/5 or better) counts as "pass".
"""
import csv
import json
import sys
from pathlib import Path

PASS = 0.5


def cohens_kappa(a: list, b: list) -> float:
    if len(a) != len(b) or not a:
        raise ValueError("need two equal-length, non-empty label lists")
    n = len(a)
    labels = sorted(set(a) | set(b))
    observed = sum(1 for x, y in zip(a, b) if x == y) / n
    expected = sum((a.count(k) / n) * (b.count(k) / n) for k in labels)
    if expected == 1:
        return 1.0
    return (observed - expected) / (1 - expected)


def export(results_file: str) -> Path:
    data = json.loads(Path(results_file).read_text())
    rows = [r for r in data["records"] if r.get("judge")]
    out = Path(results_file).with_name(Path(results_file).stem.replace("bench_", "labels_") + ".csv")
    with out.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["task", "agent", "judge_score", "judge_pass", "human_pass", "output"])
        for r in rows:
            w.writerow([r["task"], r["agent"], r["judge"]["score"], int(r["judge"]["score"] >= PASS), "", r["output"]])
    return out


def score(labels_file: str) -> dict:
    with open(labels_file, newline="") as f:
        rows = [r for r in csv.DictReader(f) if r["human_pass"].strip() in ("0", "1")]
    judge_labels = [int(r["judge_pass"]) for r in rows]
    human_labels = [int(r["human_pass"]) for r in rows]
    agree = sum(1 for x, y in zip(judge_labels, human_labels) if x == y)
    return {"n": len(rows), "agreement": round(agree / len(rows), 3) if rows else None,
            "kappa": round(cohens_kappa(judge_labels, human_labels), 3) if rows else None}


if __name__ == "__main__":
    cmd, path = sys.argv[1], sys.argv[2]
    print(export(path) if cmd == "export" else score(path))
