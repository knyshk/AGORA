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
from registry.registry import REGISTRY, get_agents_for_skill
from reputation.scoring import get_stats, route, update_score
from arbitration import resolution
from orchestration.fork import reusable_outputs
from agents.research_tools import grounded_research

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

@app.post("/agents/research-grounded")
async def research_grounded(req: TaskRequest):
    return {"output": await grounded_research(f"Task: {req.query}")}


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
    query = "Report Tesla's total revenue in 2023"
    run_id = crud.create_run(f"Conflict demo: {query}")
    return await _execute_and_record(run_id, conflict_demo_plan(), query, started)


@app.get("/runs")
def list_runs():
    return crud.list_runs()


@app.get("/runs/{run_id}")
def get_run(run_id: str):
    data = crud.get_run(run_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return data

@app.get("/runs/{run_id}/checkpoints")
def run_checkpoints(run_id: str):
    cps = crud.get_checkpoints(run_id)
    if cps is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return cps


@app.get("/runs/{run_id}/replay")
def run_replay(run_id: str, upto: int = 10**9):
    data = crud.state_at(run_id, upto)
    if data is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return data


class ForkRequest(BaseModel):
    rerun_node: str
    agent: str | None = None
    instruction: str | None = None


async def _fork(run_id: str, rerun_node: str, agent: str | None = None, instruction: str | None = None):
    data = crud.get_run(run_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Run not found")
    run, plan = data["run"], data["run"]["plan"]
    node = next((n for n in plan if n["id"] == rerun_node), None)
    if node is None:
        raise HTTPException(status_code=422, detail=f"Node '{rerun_node}' is not in this run")
    if agent:
        manifest = REGISTRY.get(agent)
        if manifest is None or manifest.skill != node["agent"]:
            raise HTTPException(status_code=422,
                                detail=f"Agent '{agent}' is not registered for skill '{node['agent']}'")

    outputs = {n["node_id"]: n["output"] for n in data["nodes"]
               if n["status"] == "done" and n["output"] is not None}
    keep = reusable_outputs(plan, outputs, rerun_node)

    started = time.time()
    new_id = crud.create_run(run["query"], parent_run_id=run_id)
    recorder = RunRecorder(new_id)
    await recorder("plan_created", {"plan": plan, "forked_from": run_id, "rerun_node": rerun_node})
    result = await execute_plan(
        plan, run["query"], emit=recorder, initial_state=keep,
        forced_agents={rerun_node: agent} if agent else None,
        instructions={rerun_node: instruction} if instruction else None,
    )
    crud.finish_run(new_id, plan, result["status"], result["conflicts"], started)
    return {"run_id": new_id, "forked_from": run_id,
            "reused_nodes": sorted(keep),
            "rerun_nodes": sorted(n["id"] for n in plan if n["id"] not in keep),
            "plan": plan, "result": result["outputs"], "conflicts": result["conflicts"],
            "node_status": result["node_status"], "status": result["status"]}


@app.post("/runs/{run_id}/fork")
async def fork_run(run_id: str, req: ForkRequest):
    return await _fork(run_id, req.rerun_node, req.agent, req.instruction)


class ResolveRequest(BaseModel):
    choice: int
    note: str = ""
    rerun: bool = False


@app.post("/runs/{run_id}/conflicts/{conflict_id}/resolve")
async def resolve_conflict(run_id: str, conflict_id: str, req: ResolveRequest):
    """Human approval gate: pick the correct side; reputation is updated; optionally re-run the loser."""
    data = crud.get_run(run_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Run not found")
    try:
        conflicts, conflict, winner, losers = resolution.resolve(
            data["run"]["conflicts"], conflict_id, req.choice, req.note)
    except resolution.ResolutionError as e:
        raise HTTPException(status_code=422, detail=str(e))

    status = resolution.run_status_after(conflicts, data["run"]["status"])
    crud.update_review(run_id, conflicts, status)
    recorder = RunRecorder.resume(run_id)
    await recorder("conflict_resolved", {"conflict_id": conflict_id, **conflict["resolution"],
                                         "label": conflict["label"], "run_status": status})
    for agent, quality, reason in resolution.reputation_updates(winner, losers, data["run"]["plan"]):
        stats = update_score(agent, quality=quality)
        await recorder("reputation_updated", {"agent": agent, "skill": REGISTRY[agent].skill if agent in REGISTRY else "",
                                              "quality": quality, "reason": f"{reason}: {conflict['label']}",
                                              "source": "conflict_resolution", "after": stats})

    fork = None
    if req.rerun and losers:
        plan_ids = [n["id"] for n in data["run"]["plan"]]
        loser = losers[0]
        target = min(loser["nodes"], key=plan_ids.index)
        fork = await _fork(run_id, target, instruction=resolution.correction_instruction(conflict, winner, loser))
    return {"conflict": conflict, "run_status": status, "conflicts": conflicts, "fork": fork}


@app.get("/reputation/scores")
def get_reputation_scores():
    """Beta posterior per agent: mean trust, 95% interval, graded runs, average quality, latency."""
    data = {}
    for name, manifest in REGISTRY.items():
        st = get_stats(name)
        data[name] = {"name": name, "skill": manifest.skill, "strategy": manifest.strategy,
                      "prior_source": getattr(manifest, "prior_source", "hand-set"),
                      "provider": manifest.provider or "default", "model": manifest.model or "default",
                      "score": st["mean"], **st}
    return data


@app.get("/reputation/route")
def explain_route(skill: str, mode: str | None = None):
    """Who would be picked for this skill right now, and why."""
    candidates = get_agents_for_skill(skill)
    if not candidates:
        raise HTTPException(status_code=404, detail=f"No agents for skill '{skill}'")
    chosen, why = route(candidates, mode=mode)
    return why


@app.get("/reputation/history")
def reputation_history(agent: str | None = None, limit: int = 200):
    """Every graded outcome (stored in the run event log), newest first."""
    return crud.events_of_type("reputation_updated", agent=agent, limit=limit)


@app.get("/runs/{run_id}/routing")
def run_routing(run_id: str):
    """Why each node in this run was given to the agent it got."""
    if crud.get_run(run_id) is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return {"routing": crud.events_of_type("agent_routed", run_id=run_id),
            "grades": crud.events_of_type("reputation_updated", run_id=run_id)}
