
from fastapi import FastAPI
from pydantic import BaseModel

from agents.base_agent import run_agent
from orchestration.planner import plan_task
from orchestration.executor import execute_plan
from orchestration.conflict_demo import conflict_demo_plan
from auth_routes import router as auth_router

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="AGORA API",
    description="Collaborative Multi-Agent AI Orchestration Platform",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router)

class TaskRequest(BaseModel):
    query: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/agents/research")
async def research(req: TaskRequest):
    output = await run_agent("research", req.query)
    return {"output": output}


@app.post("/tasks/run")
async def run_task(req: TaskRequest):
    plan = await plan_task(req.query)
    result = await execute_plan(plan, req.query)

    return {
        "plan": plan,
        "result": result["outputs"],
        "conflicts": result["conflicts"],
    }


@app.post("/tasks/conflict-demo")
async def conflict_demo():
    plan = conflict_demo_plan()

    result = await execute_plan(
        plan,
        "Conflict injection demo",
    )

    return {
        "plan": plan,
        "result": result["outputs"],
        "conflicts": result["conflicts"],
    }


@app.get("/reputation/scores")
def get_reputation_scores():
    import json
    import os
    import redis

    from registry.registry import REGISTRY
    from reputation.scoring import get_score

    # In Docker Compose this is redis://redis:6379/0.
    # When running directly on the host, use the REDIS_URL
    # configured in backend/.env.
    redis_url = os.getenv(
        "REDIS_URL",
        "redis://127.0.0.1:6379/0",
    )

    # Do not replace the Docker service hostname with localhost.
    client = redis.Redis.from_url(
        redis_url,
        decode_responses=True,
        socket_connect_timeout=3,
        socket_timeout=3,
    )

    data = {}

    for name, manifest in REGISTRY.items():
        raw = client.hget("scores", name)

        score_data = (
            json.loads(raw)
            if raw
            else {
                "prior": 0.7,
                "successes": 0,
                "total": 0,
            }
        )

        current_score = (
            get_score(name)
            if raw
            else 0.7
        )

        data[name] = {
            "name": name,
            "skill": manifest.skill,
            "provider": manifest.provider or "default",
            "model": manifest.model or "default",
            "prior": score_data.get("prior", 0.7),
            "successes": score_data.get("successes", 0),
            "total": score_data.get("total", 0),
            "score": round(float(current_score), 3),
        }

    return data
