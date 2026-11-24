import asyncio
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

import auth
from collab import routes
from collab.digest import build_digest, digest_lines
from collab.hub import Takeover, TakeoverError
from db.database import init_db
from orchestration import executor

PLAN = [{"id": "n1", "agent": "research", "depends_on": []},
        {"id": "n2", "agent": "drafting", "depends_on": ["n1"]}]


@pytest.fixture(scope="module")
def client():
    import main
    init_db()
    with TestClient(main.app) as c:
        yield c


def _user(client, name):
    email = f"{name}-{uuid.uuid4().hex[:6]}@example.com"
    r = client.post("/auth/register", json={"email": email, "password": "correct horse", "name": name})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}, r.json()["user"], email


# ---------- auth ----------

def test_password_hashing_and_tokens():
    h = auth.hash_password("correct horse")
    assert h != "correct horse" and auth.verify_password(h, "correct horse")
    assert not auth.verify_password(h, "wrong")
    assert auth.decode_token(auth.create_token("u1")) == "u1"
    with pytest.raises(Exception):
        auth.decode_token(auth.create_token("u1", ttl_s=-10))


def test_register_login_and_me(client):
    headers, user, email = _user(client, "alice")
    assert client.post("/auth/register", json={"email": email, "password": "correct horse"}).status_code == 409
    assert client.post("/auth/register", json={"email": "bad", "password": "correct horse"}).status_code == 422
    assert client.post("/auth/register", json={"email": "x@y.com", "password": "short"}).status_code == 422
    assert client.post("/auth/login", json={"email": email, "password": "nope"}).status_code == 401
    token = client.post("/auth/login", json={"email": email.upper(), "password": "correct horse"}).json()["token"]
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).json()["id"] == user["id"]
    assert client.get("/auth/me").status_code == 401


# ---------- sessions, roles, invites ----------

def test_isolated_then_collaborative_roles_and_invites(client):
    owner, _, _ = _user(client, "owner")
    guest, guest_user, _ = _user(client, "guest")
    sess = client.post("/sessions", json={"title": "Demo", "mode": "isolated"}, headers=owner).json()
    sid = sess["id"]
    assert client.get(f"/sessions/{sid}", headers=guest).status_code == 403
    assert client.post("/sessions/join", json={"token": sess["invites"]["viewer"]}, headers=guest).status_code == 403

    client.post(f"/sessions/{sid}/mode", json={"mode": "collaborative"}, headers=owner)
    joined = client.post("/sessions/join", json={"token": sess["invites"]["viewer"]}, headers=guest).json()
    assert joined["role"] == "viewer" and "invites" not in joined
    with patch.object(routes, "plan_task", new=AsyncMock(return_value=PLAN)):
        assert client.post(f"/sessions/{sid}/runs", json={"query": "q"}, headers=guest).status_code == 403
    again = client.post("/sessions/join", json={"token": sess["invites"]["editor"]}, headers=guest).json()
    assert again["role"] == "editor"
    client.post(f"/sessions/{sid}/members/{guest_user['id']}/role", json={"role": "viewer"}, headers=owner)
    assert client.get(f"/sessions/{sid}", headers=guest).json()["role"] == "viewer"
    assert client.post(f"/sessions/{sid}/members/{guest_user['id']}/role", json={"role": "owner"},
                       headers=owner).status_code == 422


def test_plan_claim_lock_and_live_websocket(client):
    alice, alice_user, _ = _user(client, "alice")
    bob, _, _ = _user(client, "bob")
    sess = client.post("/sessions", json={"title": "Live", "mode": "collaborative"}, headers=alice).json()
    sid = sess["id"]
    client.post("/sessions/join", json={"token": sess["invites"]["editor"]}, headers=bob)

    token = alice["Authorization"].split()[1]
    with client.websocket_connect(f"/ws/{sid}?token={token}") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello" and hello["you"]["role"] == "owner"
        assert ws.receive_json()["users"][0]["id"] == alice_user["id"]          # presence

        with patch.object(routes, "plan_task", new=AsyncMock(return_value=PLAN)):
            run = client.post(f"/sessions/{sid}/runs", json={"query": "q"}, headers=bob).json()
        planned = ws.receive_json()
        assert planned["type"] == "event" and planned["event"]["type"] == "plan_created"
        assert planned["event"]["payload"]["plan"] == PLAN and planned["event"]["id"] > 0

        rid = run["run_id"]
        base = f"/sessions/{sid}/runs/{rid}/nodes/n2"
        assert client.post(f"{base}/claim", headers=alice).status_code == 200
        assert ws.receive_json()["event"]["type"] == "node_claimed"
        locked = client.post(f"{base}/claim", headers=bob)
        assert locked.status_code == 409 and "locked by alice" in locked.json()["detail"]
        assert client.post(f"{base}/release", headers=bob).status_code == 409
        assert client.post(f"/sessions/{sid}/runs/{rid}/nodes/zz/claim", headers=bob).status_code == 404
        view = client.get(f"/sessions/{sid}", headers=bob).json()
        assert view["takeovers"][rid]["n2"]["user"]["name"] == "alice"

    bad = client.websocket_connect(f"/ws/{sid}?token=garbage")
    with bad as ws:
        assert ws.receive_json()["type"] == "error"


def test_digest_since_last_seen(client):
    alice, _, _ = _user(client, "alice")
    sid = client.post("/sessions", json={"title": "D", "mode": "collaborative"}, headers=alice).json()["id"]
    with patch.object(routes, "plan_task", new=AsyncMock(return_value=PLAN)):
        client.post(f"/sessions/{sid}/runs", json={"query": "Tesla revenue"}, headers=alice)
    d = client.get(f"/sessions/{sid}/digest?llm=false", headers=alice).json()
    assert d["event_count"] == 1 and "Tesla revenue" in d["lines"][0]
    client.post(f"/sessions/{sid}/seen", json={"event_id": d["latest_event_id"]}, headers=alice)
    assert client.get(f"/sessions/{sid}/digest?llm=false", headers=alice).json()["summary"] == \
        "Nothing new since you last looked."


async def test_digest_lines_and_llm_fallback():
    events = [{"id": 1, "run_id": "r", "type": "node_takeover_waiting",
               "payload": {"node_id": "n2", "skill": "drafting", "user": {"name": "Bob"}}},
              {"id": 2, "run_id": "r", "type": "agent_routed", "payload": {}},
              {"id": 3, "run_id": "r", "type": "conflict_resolved", "payload": {"label": "Tesla revenue", "value": "$96.77 billion"}}]
    lines = digest_lines(events, {"r": "Q"})
    assert len(lines) == 2 and "Bob took over node n2" in lines[0]
    with patch("collab.digest.run_agent", new=AsyncMock(side_effect=RuntimeError("429"))):
        d = await build_digest(events, {"r": "Q"})
    assert d["summary_by"] == "code" and d["latest_event_id"] == 3


# ---------- takeover in the executor ----------

async def test_takeover_rules():
    t = Takeover()
    a, b = {"id": "a", "name": "A"}, {"id": "b", "name": "B"}
    t.claim("n2", a)
    t.claim("n2", a)                       # idempotent for the holder
    with pytest.raises(TakeoverError):
        t.claim("n2", b)
    with pytest.raises(TakeoverError):
        t.submit("n2", a, "  ")
    t.mark_started("n1")
    with pytest.raises(TakeoverError):
        t.claim("n1", a)
    assert await t.wait("n2", timeout=0.01) is None and t.holder("n2") is None   # timeout frees the lock


async def _run_with_takeover(action):
    t = Takeover()
    person = {"id": "u1", "name": "Bob"}
    t.claim("n2", person)
    events = []

    async def emit(kind, payload):
        events.append(kind)
        if kind == "node_takeover_waiting":
            asyncio.get_running_loop().call_soon(action, t, person)

    async def fake(role, prompt, provider=None, model=None):
        return f"{role} agent output"

    with patch.object(executor, "run_agent", side_effect=fake), \
         patch.object(executor, "grounded_research", new=AsyncMock(return_value="research")), \
         patch.object(executor, "write_draft", new=AsyncMock(return_value="agent draft")), \
         patch.object(executor, "update_score", return_value={"mean": 0.7}) as upd, \
         patch.object(executor, "route", side_effect=lambda c: (c[0], {"reason": "x"})), \
         patch.object(executor, "arbitrate", new=AsyncMock(return_value=[])):
        result = await executor.execute_plan(PLAN, "q", emit=emit, takeover=t)
    return result, events, upd


async def test_human_output_replaces_the_agent_and_is_not_graded():
    result, events, upd = await _run_with_takeover(lambda t, p: t.submit("n2", p, "Written by Bob."))
    assert result["outputs"]["n2"] == "Written by Bob."
    assert result["node_status"]["n2"]["agent"] == "human:Bob" and result["status"] == "complete"
    assert "node_takeover_waiting" in events
    assert all(c.args[0] != "drafting-v1" for c in upd.call_args_list)


async def test_released_node_falls_back_to_an_agent():
    result, events, _ = await _run_with_takeover(lambda t, p: t.release("n2", p))
    assert result["outputs"]["n2"] == "agent draft" and "node_takeover_released" in events
