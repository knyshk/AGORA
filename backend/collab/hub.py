"""In-process live hub: WebSocket connections, presence, event broadcast and node takeover locks.

Server-authoritative: the backend owns all state, clients only send requests. Every event the
RunRecorder stores is broadcast unchanged, so live view, replay and the event log never disagree.
(Single backend process; a multi-process deployment would move this to Redis pub/sub.)
"""
import asyncio

TAKEOVER_TIMEOUT_S = 600


class TakeoverError(ValueError):
    pass


class Takeover:
    """Node locks for one run. A node can be claimed only before an agent starts it.
    While a claimed node is reached, the executor waits for the human's output instead of an agent."""

    def __init__(self):
        self.locks = {}       # node_id -> {"user": {...}, "future": Future}
        self.started = set()  # nodes already handed to an agent

    def claim(self, node_id: str, user: dict):
        if node_id in self.started:
            raise TakeoverError(f"node {node_id} has already started; it can no longer be taken over")
        lock = self.locks.get(node_id)
        if lock and lock["user"]["id"] != user["id"]:
            raise TakeoverError(f"node {node_id} is locked by {lock['user']['name']}")
        if not lock:
            self.locks[node_id] = {"user": user, "future": asyncio.get_running_loop().create_future()}
        return self.locks[node_id]

    def _own(self, node_id: str, user: dict):
        lock = self.locks.get(node_id)
        if not lock:
            raise TakeoverError(f"node {node_id} is not taken over")
        if lock["user"]["id"] != user["id"]:
            raise TakeoverError(f"node {node_id} is locked by {lock['user']['name']}")
        return lock

    def release(self, node_id: str, user: dict):
        lock = self._own(node_id, user)
        if not lock["future"].done():
            lock["future"].set_result(None)   # executor falls back to an agent
        self.locks.pop(node_id, None)

    def submit(self, node_id: str, user: dict, output: str):
        if not (output or "").strip():
            raise TakeoverError("output is empty")
        lock = self._own(node_id, user)
        if lock["future"].done():
            raise TakeoverError(f"node {node_id} is already finished")
        lock["future"].set_result(output)

    # --- executor side ---
    def holder(self, node_id: str):
        lock = self.locks.get(node_id)
        return lock["user"] if lock else None

    def mark_started(self, node_id: str):
        self.started.add(node_id)

    async def wait(self, node_id: str, timeout: float = TAKEOVER_TIMEOUT_S):
        lock = self.locks.get(node_id)
        if not lock:
            return None
        try:
            return await asyncio.wait_for(asyncio.shield(lock["future"]), timeout)
        except asyncio.TimeoutError:
            self.locks.pop(node_id, None)
            return None

    def snapshot(self) -> dict:
        return {nid: {"user": l["user"], "submitted": l["future"].done()} for nid, l in self.locks.items()}


class Hub:
    def __init__(self):
        self.connections = {}   # session_id -> {websocket: user dict}
        self.takeovers = {}     # run_id -> Takeover

    def presence(self, session_id: str) -> list:
        seen, out = set(), []
        for user in self.connections.get(session_id, {}).values():
            if user["id"] not in seen:
                seen.add(user["id"])
                out.append(user)
        return out

    async def connect(self, session_id: str, ws, user: dict):
        self.connections.setdefault(session_id, {})[ws] = user
        await self.broadcast(session_id, {"type": "presence", "users": self.presence(session_id)})

    async def disconnect(self, session_id: str, ws):
        self.connections.get(session_id, {}).pop(ws, None)
        await self.broadcast(session_id, {"type": "presence", "users": self.presence(session_id)})

    async def broadcast(self, session_id: str, message: dict):
        dead = []
        for ws in list(self.connections.get(session_id, {})):
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.connections.get(session_id, {}).pop(ws, None)

    def takeover(self, run_id: str) -> Takeover:
        return self.takeovers.setdefault(run_id, Takeover())


hub = Hub()
