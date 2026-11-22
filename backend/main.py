import time
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from agents.base_agent import run_agent
from orchestration.planner import plan_task
from orchestration.executor import execute_plan
from orchestration.conflict_demo import conflict_demo_plan
from orchestration.validation import PlanError
from db.database import init_db
from db.recorder import RunRecorder
from db import crud

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    init_db()


class TaskRequest(BaseModel):
    query: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/agents/research")
async def research(req: TaskRequest):
    return {"output": await run_agent("research", req.query)}


async def _execute_and_record(run_id: str, plan: list, query: str, started: float):
    recorder = RunRecorder(run_id)
    await recorder("plan_created", {"plan": plan})
    result = await execute_plan(plan, query, emit=recorder)
    crud.finish_run(run_id, plan, result["status"], result["conflicts"], started)
    return {"run_id": run_id, "plan": plan, "result": result["outputs"],
            "conflicts": result["conflicts"], "node_status": result["node_status"],
            "status": result["status"]}


@app.post("/tasks/run")
async def run_task(req: TaskRequest):
    started = time.time()
    run_id = crud.create_run(req.query)
    try:
        plan = await plan_task(req.query)
    except PlanError as e:
        crud.finish_run(run_id, [], "failed", [], started)
        raise HTTPException(status_code=422, detail=str(e))
    except Exception:
        crud.finish_run(run_id, [], "failed", [], started)
        raise
    return await _execute_and_record(run_id, plan, req.query, started)


@app.post("/tasks/conflict-demo")
async def conflict_demo():
    started = time.time()
    run_id = crud.create_run("Conflict injection demo")
    return await _execute_and_record(run_id, conflict_demo_plan(), "Conflict injection demo", started)


@app.get("/runs")
def list_runs():
    return crud.list_runs()


@app.get("/runs/{run_id}")
def get_run(run_id: str):
    data = crud.get_run(run_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return data


@app.get("/reputation/scores")
def get_reputation_scores():
    import json, os, redis
    from registry.registry import REGISTRY
    from reputation.scoring import get_score
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379")
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
            "score": round(float(current_score), 3),
        }
    return data