from fastapi import FastAPI
from pydantic import BaseModel
from agents.base_agent import run_agent
from orchestration.planner import plan_task
from orchestration.executor import execute_plan

app = FastAPI()

class TaskRequest(BaseModel):
    query: str

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/agents/research")
def research(req: TaskRequest):
    return {"output": run_agent("research", req.query)}



@app.post("/tasks/run")
async def run_task(req: TaskRequest):
    plan = plan_task(req.query)
    result = await execute_plan(plan, req.query)
    return {"plan": plan, "result": result}