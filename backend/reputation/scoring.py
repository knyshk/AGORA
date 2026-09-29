import redis, os, json

r = redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379"))

def seed_score(agent_name: str, prior: float):
    if r.hget("scores", agent_name) is None:
        r.hset("scores", agent_name, json.dumps({"prior": prior, "successes": 0, "total": 0}))

def update_score(agent_name: str, success: bool):
    data = json.loads(r.hget("scores", agent_name))
    data["total"] += 1
    if success:
        data["successes"] += 1
    r.hset("scores", agent_name, json.dumps(data))

def get_score(agent_name: str) -> float:
    data = json.loads(r.hget("scores", agent_name))
    if data["total"] == 0:
        return data["prior"]
    live_rate = data["successes"] / data["total"]
    weight = min(data["total"] / 20, 1.0)
    return (1 - weight) * data["prior"] + weight * live_rate

def pick_best_agent(candidates: list[str]) -> str:
    return max(candidates, key=get_score)