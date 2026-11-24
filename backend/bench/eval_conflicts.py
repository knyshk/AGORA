"""RQ2: conflict detection quality on the labelled conflict set (bench/conflicts.json).

Compares the NEW structured arbitration (claim extraction + deterministic comparison) with the
OLD baseline (one LLM call per pair asking "do these texts conflict?").

  docker compose exec backend python -m bench.eval_conflicts                 # both methods, all 64 pairs
  docker compose exec backend python -m bench.eval_conflicts --method new --ids P01,N01

A method error (e.g. unparseable LLM output) counts as "no conflict predicted". Rate limits and
timeouts are retried; if they persist, that pair is EXCLUDED for that method (it measures the free
tier, not the method) and the number of excluded pairs is reported. Results: bench/results/conflicts_<timestamp>.json and .md
"""
import argparse
import asyncio
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path

from arbitration.engine import detect_conflict
from orchestration.executor import is_infra_error
from arbitration.structured import arbitrate

HERE = Path(__file__).parent
DATA = HERE / "conflicts.json"
RESULTS = HERE / "results"


def load_pairs(ids=None):
    pairs = json.loads(DATA.read_text())["pairs"]
    return [p for p in pairs if not ids or p["id"] in ids]


async def predict_new(pair):
    errors = []

    async def emit(t, payload):
        if t == "arbitration_error":
            errors.append(payload.get("error", ""))

    conflicts = await arbitrate({"a": pair["a"], "b": pair["b"]}, {"a": "research", "b": "drafting"},
                                {"a": "eval-a", "b": "eval-b"}, emit=emit)
    return {"pred": bool(conflicts), "error": "; ".join(errors) or None,
            "detail": [c["explanation"] for c in conflicts]}


async def predict_old(pair):
    result = await detect_conflict(pair["a"], pair["b"], label_a="A", label_b="B")
    return {"pred": bool(result), "error": None, "detail": [result["explanation"]] if result else []}


METHODS = {"new": predict_new, "old": predict_old}


INFRA_RETRIES = 2
INFRA_WAIT_S = 30


def _infra(msg):
    return bool(msg) and is_infra_error(RuntimeError(msg))


async def run_method(name, pair, wait=INFRA_WAIT_S):
    for attempt in range(INFRA_RETRIES + 1):
        started = time.time()
        try:
            out = await METHODS[name](pair)
        except Exception as e:
            out = {"pred": False, "error": f"{type(e).__name__}: {str(e)[:200]}", "detail": []}
        out["latency_s"] = round(time.time() - started, 2)
        out["infra"] = _infra(out["error"])
        if not out["infra"] or attempt == INFRA_RETRIES:
            return out
        await asyncio.sleep(wait)


def wilson(k, n, z=1.96):
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(centre - half, 3), round(centre + half, 3)]


def metrics(rows, method):
    excluded = sum(1 for r in rows if r[method].get("infra"))
    rows = [r for r in rows if not r[method].get("infra")]
    tp = sum(1 for r in rows if r["label"] and r[method]["pred"])
    fp = sum(1 for r in rows if not r["label"] and r[method]["pred"])
    fn = sum(1 for r in rows if r["label"] and not r[method]["pred"])
    tn = sum(1 for r in rows if not r["label"] and not r[method]["pred"])
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = (2 * precision * recall / (precision + recall)) if precision and recall else 0.0
    by_cat = {}
    for r in rows:
        c = by_cat.setdefault(r["category"], {"n": 0, "correct": 0, "label": r["label"]})
        c["n"] += 1
        c["correct"] += int(r[method]["pred"] == r["label"])
    return {"n": len(rows), "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": round(precision, 3) if precision is not None else None,
            "recall": round(recall, 3) if recall is not None else None,
            "f1": round(f1, 3), "accuracy": round((tp + tn) / len(rows), 3) if rows else None,
            "precision_ci95": wilson(tp, tp + fp), "recall_ci95": wilson(tp, tp + fn),
            "errors": sum(1 for r in rows if r[method]["error"]), "excluded_infra": excluded,
            "mean_latency_s": round(sum(r[method]["latency_s"] for r in rows) / len(rows), 2) if rows else None,
            "by_category": by_cat}


def report_md(summary, stamp):
    lines = [f"# Conflict detection (RQ2) — {stamp}", "",
             f"Labelled pairs: {next(iter(summary.values()))['n']} (see bench/conflicts.json). "
             "Errors count as 'no conflict'. 95% Wilson intervals.", "",
             "| Method | n | Precision | Recall | F1 | Accuracy | TP | FP | FN | TN | Errors | Excluded (rate limit) | Mean latency (s) |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    names = {"new": "Structured claims (new)", "old": "Pairwise LLM (old baseline)"}
    for m, s in summary.items():
        lines.append(f"| {names[m]} | {s['n']} | {s['precision']} {s['precision_ci95']} | {s['recall']} {s['recall_ci95']} | "
                     f"{s['f1']} | {s['accuracy']} | {s['tp']} | {s['fp']} | {s['fn']} | {s['tn']} | "
                     f"{s['errors']} | {s.get('excluded_infra', 0)} | {s['mean_latency_s']} |")
    cats = sorted({c for s in summary.values() for c in s["by_category"]})
    lines += ["", "Correct per category:", "",
              "| Category | Real conflict? | " + " | ".join(names[m] for m in summary) + " |",
              "|---|---|" + "---|" * len(summary)]
    for c in cats:
        first = next(s["by_category"][c] for s in summary.values() if c in s["by_category"])
        cells = [f"{s['by_category'][c]['correct']}/{s['by_category'][c]['n']}" for s in summary.values()]
        lines.append(f"| {c} | {'yes' if first['label'] else 'no'} | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--method", choices=["new", "old", "both"], default="both")
    ap.add_argument("--ids")
    ap.add_argument("--sleep", type=float, default=4.0)
    ap.add_argument("--reuse", help="earlier results file: copy the method(s) NOT being run from it, by pair id")
    args = ap.parse_args()
    methods = ["new", "old"] if args.method == "both" else [args.method]
    pairs = load_pairs(set(args.ids.split(",")) if args.ids else None)

    rows = []
    for i, pair in enumerate(pairs, 1):
        row = {k: pair[k] for k in ("id", "label", "category", "a", "b")}
        for m in methods:
            row[m] = await run_method(m, pair)
        rows.append(row)
        marks = " ".join(f"{m}={'C' if row[m]['pred'] else '-'}{'!' if row[m]['error'] else ''}" for m in methods)
        print(f"[{i}/{len(pairs)}] {pair['id']} label={'C' if pair['label'] else '-'} {marks}")
        if i < len(pairs):
            await asyncio.sleep(args.sleep)

    if args.reuse:
        path = Path(args.reuse) if Path(args.reuse).exists() else RESULTS / args.reuse
        old_rows = {r["id"]: r for r in json.loads(path.read_text())["rows"]}
        for m in ("new", "old"):
            if m not in methods and all(m in old_rows.get(r["id"], {}) for r in rows):
                for r in rows:
                    r[m] = {**old_rows[r["id"]][m], "reused_from": path.name}
                methods.append(m)
    summary = {m: metrics(rows, m) for m in sorted(methods)}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"conflicts_{stamp}.json"
    out.write_text(json.dumps({"summary": summary, "rows": rows}, indent=1, ensure_ascii=False))
    md = report_md(summary, stamp)
    (RESULTS / f"conflicts_{stamp}.md").write_text(md)
    print("\n" + md + f"\nSaved {out}")


if __name__ == "__main__":
    asyncio.run(main())
