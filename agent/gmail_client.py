"""The agent's side of MCP: start the Gmail server as a subprocess over stdio, call its tools, stop it.

One session per check. If the server crashes the next check starts a fresh one.
"""
from __future__ import annotations

import json
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from agent.rules import Email

ROOT = Path(__file__).resolve().parent.parent


@asynccontextmanager
async def gmail_session():
    params = StdioServerParameters(command=sys.executable, args=["-m", "agent.gmail_mcp_server"], cwd=str(ROOT))
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield GmailClient(session)


def _payload(result) -> object:
    """Unwrap a CallToolResult into the JSON the tool returned."""
    if result.is_error:
        text = "; ".join(getattr(c, "text", "") for c in result.content)
        raise RuntimeError(f"gmail tool error: {text}")
    if result.structured_content:
        sc = result.structured_content
        return sc.get("result", sc) if isinstance(sc, dict) else sc
    text = "".join(getattr(c, "text", "") for c in result.content)
    return json.loads(text) if text else None


class GmailClient:
    def __init__(self, session: ClientSession):
        self.session = session

    async def tool_names(self) -> list[str]:
        tools = await self.session.list_tools()
        return sorted(t.name for t in tools.tools)

    async def profile(self) -> dict:
        return _payload(await self.session.call_tool("get_profile", {}))

    async def list_new(self, after_epoch_seconds: int, max_results: int = 50) -> list[dict]:
        out = _payload(await self.session.call_tool(
            "list_new_messages", {"after_epoch_seconds": int(after_epoch_seconds), "max_results": max_results}))
        return list(out or [])

    async def get(self, message_id: str) -> Email:
        d = _payload(await self.session.call_tool("get_message", {"message_id": message_id}))
        return Email(
            id=d["id"], sender=d.get("sender", ""), subject=d.get("subject", ""), body=d.get("body", ""),
            snippet=d.get("snippet", ""), list_unsubscribe=bool(d.get("list_unsubscribe")),
            precedence_bulk=bool(d.get("precedence_bulk")), received_at=d.get("date", ""),
        )
