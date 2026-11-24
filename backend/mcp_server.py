"""AGORA agents as a real MCP server (official `mcp` Python SDK, v2).

Served over Streamable HTTP inside the backend at http://localhost:8000/agents/mcp, and also
runnable over stdio for any MCP client:  python -m mcp_server
Tools:
  list_agents()                          the verified agents (signed manifests only)
  invoke_agent(agent, prompt, task_token) runs one agent; the task-scoped token is checked
"""
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from orchestration.executor import invoke_agent
from security import audit
from security.task_tokens import TaskTokenError
from registry.registry import REGISTRY, REJECTED

server = MCPServer(name="agora-agents", title="AGORA agents",
                   instructions="Specialised AGORA agents. Every call needs a task-scoped token issued "
                                "by the AGORA executor for exactly that agent.")


@server.tool(description="List AGORA agents whose Ed25519-signed manifest verified, and rejected manifests.")
def list_agents() -> dict:
    return {"agents": [{"name": m.name, "skill": m.skill, "provider": m.provider, "model": m.model,
                        "strategy": m.strategy, "publisher": m.publisher, "key_id": m.key_id}
                       for m in REGISTRY.values()],
            "rejected": REJECTED}


@server.tool(description="Run one AGORA agent on a prompt. Requires a valid task token for that agent.")
async def invoke_agent_tool(agent: str, prompt: str, task_token: str) -> str:
    try:
        return await invoke_agent(agent, prompt, task_token)
    except TaskTokenError as e:
        audit.record("mcp", "agent_call_refused", agent, {"reason": str(e)})
        raise ToolError(f"refused: {e}") from e


if __name__ == "__main__":
    server.run("stdio")
