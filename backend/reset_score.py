import redis
import json

r = redis.from_url("redis://localhost:6379")
r.hset("scores", "chart-v1", json.dumps({"prior": 0.7, "successes": 0, "total": 0}))
print("chart-v1 score reset")