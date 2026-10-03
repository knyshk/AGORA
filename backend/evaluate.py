import asyncio
import time
from orchestration.executor import run_node, execute_plan
from orchestration.conflict_demo import conflict_demo_plan, clean_pair_plan
from reputation.scoring import update_score, pick_best_agent, seed_score

TRIALS = 3

LATENCY_NODES = [
    {"id": "x1", "agent": "research", "depends_on": [], "forced_prompt": "In one short sentence, name the capital of France."},
    {"id": "x2", "agent": "drafting", "depends_on": [], "forced_prompt": "In one short sentence, name the capital of Japan."},
    {"id": "x3", "agent": "chart", "depends_on": [], "forced_prompt": "In one short sentence, name the capital of Germany."},
]


def reset_research_scores():
    import redis, json
    r = redis.from_url("redis://localhost:6379")
    r.hset("scores", "research-v1", json.dumps({"prior": 0.7, "successes": 0, "total": 0}))
    r.hset("scores", "research-v2", json.dumps({"prior": 0.6, "successes": 0, "total": 0}))


async def test_routing_accuracy():
    print("\n=== 1. Routing Accuracy ===")
    correct = 0
    for i in range(TRIALS):
        reset_research_scores()
        before = pick_best_agent(["research-v1", "research-v2"])
        for _ in range(5):
            update_score("research-v1", success=False)
        after = pick_best_agent(["research-v1", "research-v2"])
        flipped_correctly = (before == "research-v1" and after == "research-v2")
        print(f"Trial {i+1}: before={before}, after tanking v1 -> {after} "
              f"{'[CORRECT]' if flipped_correctly else '[WRONG]'}")
        if flipped_correctly:
            correct += 1
    print(f"Result: {correct}/{TRIALS} trials correctly routed to the better-performing agent")
    reset_research_scores()
    return correct, TRIALS


async def test_conflict_detection():
    print("\n=== 2. Conflict Detection (Precision/Recall) ===")
    true_positives = 0
    for i in range(TRIALS):
        result = await execute_plan(conflict_demo_plan(), "eval-conflict")
        flagged = len(result["conflicts"]) > 0
        print(f"Conflict trial {i+1}: flagged={flagged}")
        if flagged:
            true_positives += 1

    false_positives = 0
    for i in range(TRIALS):
        result = await execute_plan(clean_pair_plan(), "eval-clean")
        flagged = len(result["conflicts"]) > 0
        print(f"Clean-pair trial {i+1}: flagged={flagged}")
        if flagged:
            false_positives += 1

    print(f"Recall: {true_positives}/{TRIALS} real conflicts correctly caught")
    print(f"False positives: {false_positives}/{TRIALS} clean pairs wrongly flagged")
    return true_positives, false_positives, TRIALS


async def test_latency():
    print("\n=== 3. Sequential vs Parallel Latency ===")

    # Warm-up call (not timed) so connection setup doesn't bias the first real measurement
    await run_node(LATENCY_NODES[0], {}, "warmup")

    parallel_times = []
    sequential_times = []

    for trial in range(TRIALS):
        start = time.time()
        await asyncio.gather(*(run_node(n, {}, "latency test") for n in LATENCY_NODES))
        parallel_times.append(time.time() - start)

        start = time.time()
        for n in LATENCY_NODES:
            await run_node(n, {}, "latency test")
        sequential_times.append(time.time() - start)

    avg_parallel = sum(parallel_times) / TRIALS
    avg_sequential = sum(sequential_times) / TRIALS
    speedup = avg_sequential / avg_parallel if avg_parallel > 0 else 0

    print(f"Parallel times:   {[f'{t:.2f}s' for t in parallel_times]}")
    print(f"Sequential times: {[f'{t:.2f}s' for t in sequential_times]}")
    print(f"Avg parallel:   {avg_parallel:.2f}s")
    print(f"Avg sequential: {avg_sequential:.2f}s")
    print(f"Speedup:        {speedup:.2f}x")
    return avg_parallel, avg_sequential, speedup


async def main():
    r_correct, r_total = await test_routing_accuracy()
    tp, fp, total = await test_conflict_detection()
    par, seq, speedup = await test_latency()

    print("\n=== SUMMARY FOR SLIDES ===")
    print(f"Routing accuracy: {r_correct}/{r_total} correct routing decisions")
    print(f"Conflict recall: {tp}/{total} real conflicts caught")
    print(f"Conflict false-positive rate: {fp}/{total} clean pairs wrongly flagged")
    print(f"Latency: parallel {par:.2f}s vs sequential {seq:.2f}s ({speedup:.2f}x speedup)")


if __name__ == "__main__":
    asyncio.run(main())