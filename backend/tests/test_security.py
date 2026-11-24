import copy
import json
from unittest.mock import AsyncMock, patch

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import text

import mcp_server
from agents.mcp_client import call_agent_over_mcp, result_text
from db.database import SessionLocal, engine, init_db
from mcp.client.client import Client
from orchestration import executor
from registry import registry
from security import audit, manifests, task_tokens
from security.task_tokens import TaskTokenError

SPEC = {"name": "x-v1", "skill": "chart", "provider": "groq", "model": "m1", "strategy": "spec",
        "publisher": "test-pub", "version": 1}


@pytest.fixture
def keypair():
    key = Ed25519PrivateKey.generate()
    return key, {"test-pub": key.public_key()}


# ---------- signed manifests ----------

def test_valid_signature(keypair):
    key, trusted = keypair
    assert manifests.verify(manifests.sign(SPEC, key, "test-pub"), trusted) == (True, "signed by test-pub")


@pytest.mark.parametrize("field,value", [("model", "m2"), ("provider", "openrouter"), ("strategy", "plain"),
                                         ("skill", "research"), ("name", "x-v9"), ("version", 2)])
def test_any_tampered_field_is_rejected(keypair, field, value):
    key, trusted = keypair
    signed = manifests.sign(SPEC, key, "test-pub")
    signed["manifest"][field] = value
    ok, reason = manifests.verify(signed, trusted)
    assert not ok and "modified after signing" in reason


def test_unknown_key_wrong_publisher_and_malformed(keypair):
    key, trusted = keypair
    other = Ed25519PrivateKey.generate()
    assert manifests.verify(manifests.sign(SPEC, other, "evil"), trusted)[1] == "unknown signing key 'evil'"
    forged = manifests.sign(SPEC, other, "test-pub")               # right key id, wrong private key
    assert not manifests.verify(forged, trusted)[0]
    wrong_pub = manifests.sign({**SPEC, "publisher": "someone"}, key, "test-pub")
    assert manifests.verify(wrong_pub, trusted)[1] == "publisher does not match the signing key"
    assert manifests.verify({"manifest": {}}, trusted) == (False, "malformed manifest file")


def test_committed_manifests_all_verify_and_registry_rejects_tampering():
    assert len(registry.REGISTRY) == 12 and registry.REJECTED == {}
    assert all(m.verified and m.key_id == "agora-core" for m in registry.REGISTRY.values())
    signed = json.loads((manifests.MANIFEST_DIR / "chart-v1.json").read_text())
    tampered = copy.deepcopy(signed)
    tampered["manifest"]["model"] = "cheap-model"
    before = registry.REGISTRY["chart-v1"].model
    ok, reason = registry.register_signed(tampered, manifests.load_trusted_keys())
    assert not ok and registry.REGISTRY["chart-v1"].model == before


# ---------- task-scoped tokens and the agent gateway ----------

def test_task_token_scope_and_expiry():
    t = task_tokens.issue("r1", "n2", "chart-v1", "chart")
    claims = task_tokens.check(t, "chart-v1", "chart")
    assert claims["run"] == "r1" and claims["node"] == "n2"
    with pytest.raises(TaskTokenError):
        task_tokens.check(t, "chart-v2", "chart")
    with pytest.raises(TaskTokenError):
        task_tokens.check(task_tokens.issue("r1", "n2", "chart-v1", "chart", ttl_s=-5), "chart-v1", "chart")
    with pytest.raises(TaskTokenError):
        task_tokens.check("forged", "chart-v1", "chart")


async def test_gateway_requires_matching_token_and_verified_manifest():
    with patch.object(executor, "_dispatch", new=AsyncMock(return_value="ok")) as run:
        assert await executor.invoke_agent("chart-v1", "p", task_tokens.issue("r", "n", "chart-v1", "chart")) == "ok"
        with pytest.raises(TaskTokenError):
            await executor.invoke_agent("chart-v1", "p", task_tokens.issue("r", "n", "research-v1", "research"))
        with pytest.raises(TaskTokenError):
            await executor.invoke_agent("not-registered", "p", "x")
    assert run.await_count == 1


# ---------- audit log ----------

def test_audit_chain_append_only_and_tamper_detection():
    init_db()
    audit.record("tester", "test_event", "t1", {"a": 1})
    audit.record("tester", "test_event", "t2", {"a": 2})
    assert audit.verify_chain()["ok"]
    with pytest.raises(Exception):
        with engine.begin() as conn:
            conn.execute(text("UPDATE audit_log SET actor='attacker'"))
    with pytest.raises(Exception):
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM audit_log"))
    with engine.begin() as conn:   # an insert that skips record() cannot fake the chain
        conn.execute(text("INSERT INTO audit_log (created_at, actor, action, target, detail, prev_hash, hash) "
                          "VALUES (CURRENT_TIMESTAMP, 'attacker', 'forged', '', '{}', 'x', 'y')"))
    result = audit.verify_chain()
    assert not result["ok"] and result["broken_at"] > 0
    with SessionLocal() as s:   # keep later tests independent of the broken chain
        s.execute(text("DROP TRIGGER IF EXISTS audit_log_no_delete"))
        s.execute(text("DELETE FROM audit_log"))
        s.commit()
    init_db()


# ---------- real MCP (in-memory transport) ----------

async def test_mcp_server_lists_agents_and_refuses_bad_tokens():
    async with Client(mcp_server.server) as client:
        names = [t.name for t in (await client.list_tools()).tools]
        assert names == ["list_agents", "invoke_agent_tool"]
        listed = json.loads(result_text(await client.call_tool("list_agents", {})))
        assert len(listed["agents"]) == 12
        bad = await client.call_tool("invoke_agent_tool", {"agent": "chart-v1", "prompt": "p", "task_token": "forged"})
        assert "refused" in " ".join(c.text for c in bad.content)


async def test_agent_call_over_mcp_end_to_end():
    with patch.object(executor, "_dispatch", new=AsyncMock(return_value="chart output")):
        token = task_tokens.issue("r", "n3", "chart-v1", "chart")
        assert await call_agent_over_mcp("chart-v1", "p", token, target=mcp_server.server) == "chart output"
        with pytest.raises(Exception, match="refused"):
            await call_agent_over_mcp("chart-v1", "p", "forged", target=mcp_server.server)
