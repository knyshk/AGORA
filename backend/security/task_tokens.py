"""Short-lived, task-scoped tokens for agent calls.

The executor issues one token per node call (run, node, agent, skill; valid TTL_S seconds). The
agent gateway (direct call or the MCP server) refuses to run unless the token is valid AND names
exactly that agent and skill. A leaked token is useless for any other agent or after it expires.
"""
import time
import uuid

import jwt

from auth import JWT_ALGORITHM, jwt_secret

AUDIENCE = "agora-agent"
TTL_S = 120


class TaskTokenError(PermissionError):
    pass


def issue(run_id: str, node_id: str, agent: str, skill: str, ttl_s: int = TTL_S) -> str:
    now = int(time.time())
    claims = {"aud": AUDIENCE, "iat": now, "exp": now + ttl_s, "jti": uuid.uuid4().hex,
              "run": run_id, "node": node_id, "agent": agent, "skill": skill, "scope": "agent:invoke"}
    return jwt.encode(claims, jwt_secret(), algorithm=JWT_ALGORITHM)


def check(token: str, agent: str, skill: str) -> dict:
    try:
        claims = jwt.decode(token or "", jwt_secret(), algorithms=[JWT_ALGORITHM], audience=AUDIENCE)
    except jwt.PyJWTError as e:
        raise TaskTokenError(f"task token rejected: {type(e).__name__}")
    if claims.get("scope") != "agent:invoke" or claims.get("agent") != agent or claims.get("skill") != skill:
        raise TaskTokenError(f"task token is for {claims.get('agent')}/{claims.get('skill')}, not {agent}/{skill}")
    return claims
