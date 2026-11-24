import os
import random
from concurrent.futures import ThreadPoolExecutor

import pytest
import redis

from reputation import scoring as sc

TEST_DB = os.getenv("TEST_REDIS_URL", "redis://redis:6379/15")  # separate DB, never the real scores (db 0)


@pytest.fixture(autouse=True)
def test_redis(monkeypatch):
    client = redis.from_url(TEST_DB)
    try:
        client.ping()
    except redis.exceptions.ConnectionError:
        pytest.skip("Redis not reachable (run tests inside docker compose)")
    client.flushdb()
    monkeypatch.setattr(sc, "r", client)
    monkeypatch.setattr(sc, "_UPDATE", client.register_script(sc._UPDATE.script))
    yield
    client.flushdb()


def test_seed_gives_prior_mean():
    sc.seed_score("a", 0.7)
    st = sc.get_stats("a")
    assert st["mean"] == pytest.approx(0.7)
    assert st["n"] == 0 and st["avg_quality"] is None
    assert st["ci95"][0] < 0.7 < st["ci95"][1]


def test_quality_moves_the_posterior_with_decay():
    sc.seed_score("a", 0.5)
    sc.update_score("a", quality=1.0)
    after_one = sc.get_stats("a")
    sc.update_score("a", quality=1.0)
    raw = sc.r.hgetall("rep:a")
    assert float(raw[b"a_ev"]) == pytest.approx(1.0 * sc.DECAY + 1.0)
    assert sc.get_stats("a")["mean"] > after_one["mean"] > 0.5
    sc.update_score("a", quality=0.0)
    assert sc.get_stats("a")["n"] == 3
    assert sc.get_stats("a")["avg_quality"] == pytest.approx(2 / 3, abs=1e-3)


def test_reseeding_changes_prior_but_keeps_evidence():
    sc.seed_score("a", 0.5)
    sc.update_score("a", quality=1.0)
    sc.seed_score("a", 0.9)
    st = sc.get_stats("a")
    assert st["prior"] == 0.9 and st["n"] == 1


def test_updates_are_atomic_under_concurrency():
    sc.seed_score("a", 0.5)
    with ThreadPoolExecutor(8) as pool:
        list(pool.map(lambda _: sc.update_score("a", quality=1.0), range(60)))
    assert sc.get_stats("a")["n"] == 60
    assert sc.get_stats("a")["avg_quality"] == pytest.approx(1.0)


def test_greedy_fixed_random_and_success_rate_modes():
    sc.seed_score("good", 0.5)
    sc.seed_score("bad", 0.5)
    for _ in range(5):
        sc.update_score("good", quality=1.0)
        sc.update_score("bad", quality=0.0)
    assert sc.route(["bad", "good"], mode="greedy")[0] == "good"
    assert sc.route(["bad", "good"], mode="success_rate")[0] == "good"
    assert sc.route(["bad", "good"], mode="fixed")[0] == "bad"
    picks = {sc.route(["bad", "good"], mode="random", rng=random.Random(s))[0] for s in range(20)}
    assert picks == {"bad", "good"}


def test_thompson_mostly_picks_better_agent_and_explains():
    sc.seed_score("good", 0.5)
    sc.seed_score("bad", 0.5)
    for _ in range(10):
        sc.update_score("good", quality=0.9)
        sc.update_score("bad", quality=0.2)
    rng = random.Random(0)
    picks = [sc.route(["bad", "good"], mode="thompson", rng=rng)[0] for _ in range(100)]
    assert picks.count("good") > 90
    chosen, why = sc.route(["bad", "good"], mode="thompson", rng=random.Random(1))
    assert why["mode"] == "thompson" and len(why["candidates"]) == 2
    assert chosen in why["reason"] and "95% CI" in why["reason"]


def test_latency_breaks_ties_in_favour_of_faster_agent():
    sc.seed_score("fast", 0.7)
    sc.seed_score("slow", 0.7)
    sc.update_score("fast", quality=0.8, latency_s=2.0)
    sc.update_score("slow", quality=0.8, latency_s=20.0)
    assert sc.route(["slow", "fast"], mode="greedy")[0] == "fast"


def test_reset_keeps_priors():
    sc.seed_score("a", 0.8)
    sc.update_score("a", quality=0.0, latency_s=3)
    sc.reset_scores()
    st = sc.get_stats("a")
    assert st["n"] == 0 and st["prior"] == 0.8 and st["latency_s"] is None


def test_unmeasured_latency_gets_no_free_bonus():
    sc.seed_score("measured", 0.75)
    sc.seed_score("new", 0.65)
    sc.r.hset("rep:measured", "lat_ema", 5.0)
    assert sc.route(["new", "measured"], mode="greedy")[0] == "measured"
