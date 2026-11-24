"""Call an agent through the MCP server (used when AGENT_TRANSPORT=mcp)."""
import os

from mcp.client.client import Client

MCP_URL = os.getenv("MCP_URL", "http://localhost:8000/agents/mcp")
TIMEOUT_S = 180


class MCPToolError(RuntimeError):
    pass


def result_text(result) -> str:
    texts = [c.text for c in (result.content or []) if getattr(c, "type", "") == "text"]
    if getattr(result, "is_error", False) or getattr(result, "isError", False):
        raise MCPToolError("; ".join(texts) or "MCP tool call failed")
    return "\n".join(texts)


async def call_agent_over_mcp(agent: str, prompt: str, task_token: str, target=None) -> str:
    async with Client(target or MCP_URL, read_timeout_seconds=TIMEOUT_S) as client:
        result = await client.call_tool("invoke_agent_tool",
                                        {"agent": agent, "prompt": prompt, "task_token": task_token})
    return result_text(result)
