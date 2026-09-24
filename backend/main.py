from fastapi import FastAPI
from pydantic import BaseModel
from agents.base_agent import run_agent

app = FastAPI()

class TaskRequest(BaseModel):
    query: str

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/agents/research")
def research(req: TaskRequest):
    return {"output": run_agent("research", req.query)}