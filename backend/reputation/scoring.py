"""Bayesian reputation: one Beta distribution per agent.

- Prior: Beta(p * S, (1 - p) * S) where p is the agent's prior (from the registry, later from
  AGORA-Bench) and S = PRIOR_STRENGTH pseudo-observations.
- Evidence: every graded outcome with quality q in [0, 1] adds q to alpha and (1 - q) to beta.
  Old evidence decays by DECAY per update, so an agent that gets worse is noticed.
- Updates run as one Lua script in Redis, so concurrent nodes cannot lose an update.
- Routing modes (ROUTING_MODE env var), so evaluation can compare against baselines:
    thompson      sample each candidate's Beta, pick the best (default; explores and exploits)
    greedy        pick the highest posterior mean
    success_rate  old-style raw average quality (baseline)
    random        uniform random (baseline)
    fixed         always the first registered candidate (baseline)
  thompson and greedy multiply by a small latency fit term (faster agents preferred on ties).
- Infrastructure errors are never passed in here (see executor.is_infra_error).
"""
import math
import os
import random

import redis

r = redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379"))

PRIOR_STRENGTH = 10.0
MIN_PRIOR_STRENGTH = 2.0   # the benchmark prior fades as live evidence accumulates, but never below this
DECAY = 0.97
LATENCY_WEIGHT = 0.15
MODES = ("thompson", "greedy", "success_rate", "random", "fixed")


def _key(name: str) -> str:
    return f"rep:{name}"


_UPDATE = r.register_script("""
local k = KEYS[1]
local q = tonumber(ARGV[1])
local decay = tonumber(ARGV[2])
local a = tonumber(redis.call('HGET', k, 'a_ev') or '0') * decay + q
local b = tonumber(redis.call('HGET', k, 'b_ev') or '0') * decay + (1 - q)
local pw = math.max(tonumber(ARGV[5]), tonumber(redis.call('HGET', k, 'pw') or ARGV[4]) * decay)
redis.call('HSET', k, 'a_ev', tostring(a), 'b_ev', tostring(b), 'pw', tostring(pw))
redis.call('HINCRBY', k, 'n', 1)
redis.call('HINCRBYFLOAT', k, 'quality_sum', q)
if ARGV[3] ~= '' then
  local lat = tonumber(ARGV[3])
  local e = tonumber(redis.call('HGET', k, 'lat_ema') or '-1')
  if e < 0 then e = lat else e = 0.7 * e + 0.3 * lat end
  redis.call('HSET', k, 'lat_ema', tostring(e))
end
return 1
""")


def seed_score(agent_name: str, prior: float):
    """Set the prior (always refreshed, so benchmark-derived priors take effect); keep evidence."""
    k = _key(agent_name)
    r.hset(k, "prior", prior)
    for field in ("a_ev", "b_ev", "n", "quality_sum"):
        r.hsetnx(k, field, 0)


def reset_scores():
    for k in r.scan_iter("rep:*"):
        r.hset(k, mapping={"a_ev": 0, "b_ev": 0, "n": 0, "quality_sum": 0, "pw": PRIOR_STRENGTH})
        r.hdel(k, "lat_ema")


def get_stats(agent_name: str) -> dict:
    raw = {k.decode(): v.decode() for k, v in r.hgetall(_key(agent_name)).items()}
    prior = float(raw.get("prior", 0.7))
    pw = float(raw.get("pw", PRIOR_STRENGTH))   # current weight of the benchmark prior
    a = prior * pw + float(raw.get("a_ev", 0))
    b = (1 - prior) * pw + float(raw.get("b_ev", 0))
    mean = a / (a + b)
    sd = math.sqrt(a * b / ((a + b) ** 2 * (a + b + 1)))
    n = int(float(raw.get("n", 0)))
    qsum = float(raw.get("quality_sum", 0))
    lat = float(raw["lat_ema"]) if "lat_ema" in raw else None
    return {"agent": agent_name, "prior": prior, "alpha": round(a, 3), "beta": round(b, 3),
            "mean": round(mean, 4), "ci95": [round(max(0, mean - 1.96 * sd), 3), round(min(1, mean + 1.96 * sd), 3)],
            "n": n, "avg_quality": round(qsum / n, 3) if n else None,
            "latency_s": round(lat, 2) if lat is not None else None, "prior_weight": round(pw, 2)}


def get_score(agent_name: str) -> float:
    return get_stats(agent_name)["mean"]


def update_score(agent_name: str, success: bool = None, quality: float = None, latency_s: float = None) -> dict:
    q = float(quality) if quality is not None else (1.0 if success else 0.0)
    q = min(1.0, max(0.0, q))
    _UPDATE(keys=[_key(agent_name)], args=[q, DECAY, "" if latency_s is None else latency_s,
                                           PRIOR_STRENGTH, MIN_PRIOR_STRENGTH])
    return get_stats(agent_name)


def route(candidates: list, mode: str = None, rng: random.Random = None, stats_fn=None) -> tuple:
    """Choose an agent and explain why. Returns (chosen, explanation dict).
    stats_fn lets the routing simulator use in-memory statistics with exactly this code."""
    mode = mode or os.getenv("ROUTING_MODE", "thompson")
    if mode not in MODES:
        mode = "thompson"
    rng = rng or random
    stats = [(stats_fn or get_stats)(c) for c in candidates]
    latencies = [s["latency_s"] for s in stats if s["latency_s"]]
    slowest = max(latencies) if latencies else None
    typical = sum(latencies) / len(latencies) if latencies else None  # unmeasured agents count as average

    rows = []
    for s in stats:
        latency = s["latency_s"] or typical
        if mode == "thompson":
            value = rng.betavariate(s["alpha"], s["beta"])
        elif mode == "success_rate":
            value = s["avg_quality"] if s["avg_quality"] is not None else s["prior"]
        else:
            value = s["mean"]
        fit = 1.0
        if mode in ("thompson", "greedy") and slowest and latency:
            fit = 1 - LATENCY_WEIGHT * (latency / slowest)
        rows.append({**s, "value": round(value, 4), "fit": round(fit, 3), "utility": round(value * fit, 4)})

    if mode == "random":
        chosen = rng.choice(candidates)
    elif mode == "fixed":
        chosen = candidates[0]
    else:
        chosen = max(rows, key=lambda x: x["utility"])["agent"]

    best = next(x for x in rows if x["agent"] == chosen)
    if mode in ("random", "fixed"):
        reason = f"{mode} baseline routing picked {chosen}"
    else:
        others = ", ".join(f"{x['agent']} {x['utility']:.3f}" for x in rows if x["agent"] != chosen)
        label = {"thompson": "sampled trust x speed", "greedy": "mean trust x speed",
                 "success_rate": "raw average quality"}[mode]
        reason = (f"{chosen} won on {label}: {best['utility']:.3f}"
                  + (f" vs {others}" if others else "")
                  + f" (trust mean {best['mean']:.3f}, 95% CI {best['ci95'][0]}-{best['ci95'][1]}, "
                    f"{best['n']} graded runs)")
    return chosen, {"mode": mode, "chosen": chosen, "reason": reason, "candidates": rows}


def pick_best_agent(candidates: list) -> str:
    return route(candidates)[0]


def posterior(prior: float, a_ev: float, b_ev: float, n: int, quality_sum: float, latency=None, name="",
              prior_weight: float = PRIOR_STRENGTH) -> dict:
    """The same statistics as get_stats, from plain numbers (used by the routing simulator)."""
    a = prior * prior_weight + a_ev
    b = (1 - prior) * prior_weight + b_ev
    mean = a / (a + b)
    sd = math.sqrt(a * b / ((a + b) ** 2 * (a + b + 1)))
    return {"agent": name, "prior": prior, "alpha": a, "beta": b, "mean": mean,
            "ci95": [max(0, mean - 1.96 * sd), min(1, mean + 1.96 * sd)], "n": n,
            "avg_quality": quality_sum / n if n else None, "latency_s": latency}
