"""HTTP + WebSocket API for live collaboration."""
import asyncio
import time

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

import auth
from security import audit
from collab import service
from collab.digest import build_digest
from collab.hub import TakeoverError, hub
from db import crud
from db.models import User
from db.recorder import RunRecorder
from orchestration.executor import execute_plan
from orchestration.planner import plan_task
from orchestration.validation import PlanError

router = APIRouter()


# ---------------- auth ----------------

class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str = ""


class LoginRequest(BaseModel):
    email: str
    password: str


@router.post("/auth/register")
def register(req: RegisterRequest):
    user = auth.register(req.email, req.password, req.name)
    audit.record(f"user:{user.id}", "user_registered", user.email)
    return {"token": auth.create_token(user.id), "user": auth.public_user(user)}


@router.post("/auth/login")
def login(req: LoginRequest):
    user = auth.login(req.email, req.password)
    audit.record(f"user:{user.id}", "user_login", user.email)
    return {"token": auth.create_token(user.id), "user": auth.public_user(user)}


@router.get("/auth/me")
def me(user: User = Depends(auth.current_user)):
    return auth.public_user(user)


# ---------------- sessions ----------------

class SessionCreate(BaseModel):
    title: str
    mode: str = "isolated"


class ModeRequest(BaseModel):
    mode: str


class JoinRequest(BaseModel):
    token: str


class RoleRequest(BaseModel):
    role: str


def _live(session_id: str):
    async def on_event(event: dict):
        await hub.broadcast(session_id, {"type": "event", "event": event})
    return on_event


def _session_view(sess, role: str) -> dict:
    view = {"id": sess.id, "title": sess.title, "mode": sess.mode, "role": role,
            "members": service.members(sess.id), "online": hub.presence(sess.id),
            "runs": service.runs_of(sess.id),
            "takeovers": {r["id"]: hub.takeover(r["id"]).snapshot() for r in service.runs_of(sess.id)},
            "controls": {r["id"]: hub.control(r["id"]).snapshot() for r in service.runs_of(sess.id)}}
    if role == "owner":
        view["invites"] = {"editor": sess.editor_token, "viewer": sess.viewer_token}
    return view


@router.post("/sessions")
def create_session(req: SessionCreate, user: User = Depends(auth.current_user)):
    sess = service.create_session(user, req.title, req.mode)
    return _session_view(sess, "owner")


@router.get("/sessions")
def my_sessions(user: User = Depends(auth.current_user)):
    return service.sessions_for(user)


@router.get("/sessions/{session_id}")
def get_session(session_id: str, user: User = Depends(auth.current_user)):
    sess, role = service.require_role(session_id, user, "viewer")
    return _session_view(sess, role)


@router.post("/sessions/{session_id}/mode")
async def set_mode(session_id: str, req: ModeRequest, user: User = Depends(auth.current_user)):
    service.require_role(session_id, user, "owner")
    sess = service.set_mode(session_id, req.mode)
    audit.record(f"user:{user.id}", "session_mode_changed", session_id, {"mode": req.mode})
    await hub.broadcast(session_id, {"type": "mode", "mode": sess.mode})
    return _session_view(sess, "owner")


@router.post("/sessions/join")
async def join(req: JoinRequest, user: User = Depends(auth.current_user)):
    sess, role = service.join_with_token(user, req.token)
    audit.record(f"user:{user.id}", "session_joined", sess.id, {"role": role})
    await hub.broadcast(sess.id, {"type": "members", "members": service.members(sess.id)})
    return _session_view(sess, role)


@router.post("/sessions/{session_id}/members/{user_id}/role")
async def set_role(session_id: str, user_id: str, req: RoleRequest, user: User = Depends(auth.current_user)):
    service.require_role(session_id, user, "owner")
    service.set_member_role(session_id, user_id, req.role)
    audit.record(f"user:{user.id}", "member_role_changed", session_id, {"member": user_id, "role": req.role})
    await hub.broadcast(session_id, {"type": "members", "members": service.members(session_id)})
    return {"members": service.members(session_id)}


# ---------------- runs inside a session: plan -> (claim nodes) -> start ----------------

class SessionRunRequest(BaseModel):
    query: str
    local_only: bool = False   # plan and run on the laptop's model (no cloud LLM, no rate limits)


class SubmitRequest(BaseModel):
    output: str


_tasks = set()  # keep background run tasks referenced


@router.post("/sessions/{session_id}/runs")
async def plan_run(session_id: str, req: SessionRunRequest, user: User = Depends(auth.current_user)):
    """Plan only. Members can now take over nodes before an editor starts the run."""
    service.require_role(session_id, user, "editor")
    run_id = crud.create_run(req.query)
    service.link_run(session_id, run_id)
    if req.local_only:
        from agents.base_agent import force_provider
        force_provider("ollama")
    try:
        plan = await plan_task(req.query)
    except PlanError as e:
        crud.set_plan(run_id, [], "failed")
        raise HTTPException(status_code=422, detail=str(e))
    crud.set_plan(run_id, plan, "planned")
    await RunRecorder(run_id, _live(session_id))("plan_created", {"plan": plan, "by": auth.public_user(user),
                                                                  "local_only": req.local_only})
    return {"run_id": run_id, "plan": plan, "status": "planned"}


def _session_run(session_id: str, run_id: str) -> dict:
    if service.session_of_run(run_id) != session_id:
        raise HTTPException(status_code=404, detail="Run is not in this session")
    return crud.get_run(run_id)["run"]


async def _execute(session_id: str, run_id: str, plan: list, query: str, local_only: bool = False):
    started = time.time()
    recorder = RunRecorder.resume(run_id, _live(session_id))
    try:
        async def stream(payload):   # live-only token stream to everyone in the session
            await hub.broadcast(session_id, {"type": "stream", "run_id": run_id, **payload})
        result = await execute_plan(plan, query, emit=recorder, takeover=hub.takeover(run_id), stream=stream,
                                    control=hub.control(run_id), local_only=local_only)
        crud.finish_run(run_id, plan, result["status"], result["conflicts"], started)
    except Exception as e:
        crud.finish_run(run_id, plan, "failed", [], started)
        await recorder("run_finished", {"status": "failed", "error": f"{type(e).__name__}: {str(e)[:200]}"})


@router.post("/sessions/{session_id}/runs/{run_id}/start")
async def start_run(session_id: str, run_id: str, user: User = Depends(auth.current_user)):
    service.require_role(session_id, user, "editor")
    run = _session_run(session_id, run_id)
    if run["status"] != "planned":
        raise HTTPException(status_code=409, detail=f"Run is already {run['status']}")
    crud.set_plan(run_id, run["plan"], "running")
    events = crud.get_run(run_id)["events"]
    local_only = any(e["type"] == "plan_created" and e["payload"].get("local_only") for e in events)
    task = asyncio.create_task(_execute(session_id, run_id, run["plan"], run["query"], local_only))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return {"run_id": run_id, "status": "running"}


async def _takeover_action(session_id, run_id, node_id, user, action, output=None):
    service.require_role(session_id, user, "editor")
    run = _session_run(session_id, run_id)
    if node_id not in {n["id"] for n in run["plan"]}:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' is not in this run")
    who = auth.public_user(user)
    to = hub.takeover(run_id)
    try:
        if action == "claim":
            to.claim(node_id, who)
        elif action == "release":
            to.release(node_id, who)
        else:
            to.submit(node_id, who, output)
    except TakeoverError as e:
        raise HTTPException(status_code=409, detail=str(e))
    event = {"claim": "node_claimed", "release": "node_released", "submit": "node_submitted"}[action]
    audit.record(f"user:{user.id}", event, f"{run_id}/{node_id}")
    await RunRecorder.resume(run_id, _live(session_id))(event, {"node_id": node_id, "user": who})
    return {"takeovers": to.snapshot()}


@router.post("/sessions/{session_id}/runs/{run_id}/nodes/{node_id}/claim")
async def claim(session_id: str, run_id: str, node_id: str, user: User = Depends(auth.current_user)):
    return await _takeover_action(session_id, run_id, node_id, user, "claim")


@router.post("/sessions/{session_id}/runs/{run_id}/nodes/{node_id}/release")
async def release(session_id: str, run_id: str, node_id: str, user: User = Depends(auth.current_user)):
    return await _takeover_action(session_id, run_id, node_id, user, "release")


@router.post("/sessions/{session_id}/runs/{run_id}/nodes/{node_id}/submit")
async def submit(session_id: str, run_id: str, node_id: str, req: SubmitRequest,
                 user: User = Depends(auth.current_user)):
    return await _takeover_action(session_id, run_id, node_id, user, "submit", req.output)


# ---------------- mid-task control of a single node (pause / resume / redirect / reassign) ----------------

class ControlRequest(BaseModel):
    instruction: str | None = None
    agent: str | None = None


@router.post("/sessions/{session_id}/runs/{run_id}/nodes/{node_id}/{action}")
async def control_node(session_id: str, run_id: str, node_id: str, action: str, req: ControlRequest,
                       user: User = Depends(auth.current_user)):
    from orchestration.control import ControlError
    from registry.registry import REGISTRY
    if action not in ("pause", "resume", "redirect", "reassign"):
        raise HTTPException(status_code=404, detail=f"Unknown action '{action}'")
    service.require_role(session_id, user, "editor")
    run = _session_run(session_id, run_id)
    node = next((n for n in run["plan"] if n["id"] == node_id), None)
    if node is None:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' is not in this run")
    if req.agent and (req.agent not in REGISTRY or REGISTRY[req.agent].skill != node["agent"]):
        raise HTTPException(status_code=422, detail=f"'{req.agent}' is not a registered {node['agent']} agent")
    control = hub.control(run_id)
    try:
        if action == "pause":
            control.pause(node_id)
        elif action == "resume":
            control.resume(node_id, req.instruction, req.agent)
        elif action == "redirect":
            control.redirect(node_id, req.instruction or "")
        else:
            if not req.agent:
                raise HTTPException(status_code=422, detail="reassign needs an agent")
            control.reassign(node_id, req.agent)
    except ControlError as e:
        raise HTTPException(status_code=409, detail=str(e))
    who = auth.public_user(user)
    kind = {"pause": "node_paused", "resume": "node_resumed", "redirect": "node_redirected",
            "reassign": "node_reassigned"}[action]
    payload = {"node_id": node_id, "user": who, "instruction": req.instruction, "agent": req.agent}
    await RunRecorder.resume(run_id, _live(session_id))(kind, payload)
    audit.record(f"user:{user.id}", kind, f"{run_id}/{node_id}", {"instruction": req.instruction, "agent": req.agent})
    return {"controls": control.snapshot()}


# ---------------- catch-up digest ----------------

class SeenRequest(BaseModel):
    event_id: int


@router.get("/sessions/{session_id}/digest")
async def digest(session_id: str, llm: bool = True, user: User = Depends(auth.current_user)):
    service.require_role(session_id, user, "viewer")
    me_ = next(m for m in service.members(session_id) if m["user_id"] == user.id)
    events = service.events_since(session_id, me_["last_seen_event_id"])
    queries = {r["id"]: r["query"] for r in service.runs_of(session_id)}
    return {"since_event_id": me_["last_seen_event_id"], **(await build_digest(events, queries, use_llm=llm))}


@router.post("/sessions/{session_id}/seen")
def seen(session_id: str, req: SeenRequest, user: User = Depends(auth.current_user)):
    service.require_role(session_id, user, "viewer")
    service.mark_seen(session_id, user.id, req.event_id)
    return {"ok": True}


# ---------------- live WebSocket ----------------

@router.websocket("/ws/{session_id}")
async def live(ws: WebSocket, session_id: str, token: str = ""):
    await ws.accept()
    try:
        user = auth.user_from_token(token)
        sess, role = service.require_role(session_id, user, "viewer")
    except HTTPException as e:
        await ws.send_json({"type": "error", "detail": e.detail})
        await ws.close(code=4401)
        return
    who = {**auth.public_user(user), "role": role}
    await ws.send_json({"type": "hello", "you": who, "session": _session_view(sess, role)})
    await hub.connect(session_id, ws, who)
    try:
        while True:
            msg = await ws.receive_json()
            if msg.get("type") == "seen" and isinstance(msg.get("event_id"), int):
                service.mark_seen(session_id, user.id, msg["event_id"])
            elif msg.get("type") == "ping":
                await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        await hub.disconnect(session_id, ws)
