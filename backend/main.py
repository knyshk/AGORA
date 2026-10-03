from fastapi import FastAPI
from pydantic import BaseModel
from agents.base_agent import run_agent
from orchestration.planner import plan_task
from orchestration.executor import execute_plan
from orchestration.conflict_demo import conflict_demo_plan

app = FastAPI()

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class TaskRequest(BaseModel):
    query: str

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/agents/research")
async def research(req: TaskRequest):
    return {"output": await run_agent("research", req.query)}

@app.post("/tasks/run")
async def run_task(req: TaskRequest):
    plan = await plan_task(req.query)
    result = await execute_plan(plan, req.query)
    return {"plan": plan, "result": result["outputs"], "conflicts": result["conflicts"]}

@app.post("/tasks/conflict-demo")
async def conflict_demo():
    plan = conflict_demo_plan()
    result = await execute_plan(plan, "Conflict injection demo")
    return {"plan": plan, "result": result["outputs"], "conflicts": result["conflicts"]}

@app.get("/reputation/scores")
def get_reputation_scores():
    import json, os, redis
    from registry.registry import REGISTRY
    from reputation.scoring import get_score
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379").replace("redis://redis:6379", "redis://localhost:6379")
    r = redis.from_url(redis_url)
    data = {}
    for name, manifest in REGISTRY.items():
        raw = r.hget("scores", name)
        score_data = json.loads(raw.decode("utf-8")) if raw else {"prior": 0.7, "successes": 0, "total": 0}
        current_score = get_score(name) if raw else 0.7
        data[name] = {
            "name": name,
            "skill": manifest.skill,
            "provider": manifest.provider or "default",
            "model": manifest.model or "default",
            "prior": score_data.get("prior", 0.7),
            "successes": score_data.get("successes", 0),
            "total": score_data.get("total", 0),
            "score": round(float(current_score), 3)
        }
    return data