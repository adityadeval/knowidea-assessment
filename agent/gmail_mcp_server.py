"""The email MCP server: a read-only Gmail server over stdio.

Read-only twice over:
  1. The OAuth scope is gmail.readonly. Google rejects any write with this token.
  2. The server exposes three tools, all reads. There is no delete, send, modify or trash tool to call.

Run on its own for a smoke test:  python -m agent.gmail_mcp_server   (then speak MCP on stdin, or use the client).
The agent starts it as a subprocess through agent/gmail_client.py.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from mcp.server.mcpserver import MCPServer

from agent.config import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
GMAIL = "https://gmail.googleapis.com/gmail/v1/users/me"

mcp = MCPServer("gmail-readonly")


def credentials() -> Credentials:
    token_path = ROOT / "token.json"
    if not token_path.exists():
        raise RuntimeError("token.json missing: run `python -m agent.auth_gmail` first")
    creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            token_path.write_text(creds.to_json(), encoding="utf-8")
        else:
            raise RuntimeError("token.json is not valid and cannot be refreshed: run `python -m agent.auth_gmail`")
    return creds


def gmail_get(path: str, params: dict | None = None) -> dict:
    creds = credentials()
    r = requests.get(f"{GMAIL}/{path}", params=params or {},
                     headers={"Authorization": f"Bearer {creds.token}"}, timeout=30)
    r.raise_for_status()
    return r.json()


def _header(headers: list[dict], name: str) -> str:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def _decode(data: str) -> str:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", errors="replace")


def _text_of(payload: dict) -> str:
    """Depth-first search for the first text/plain part; falls back to text/html with tags stripped crudely."""
    plain, html = [], []

    def walk(part: dict) -> None:
        mime = part.get("mimeType", "")
        body = part.get("body", {}) or {}
        data = body.get("data")
        if data and mime == "text/plain":
            plain.append(_decode(data))
        elif data and mime == "text/html":
            html.append(_decode(data))
        for p in part.get("parts", []) or []:
            walk(p)

    walk(payload)
    if plain:
        return "\n".join(plain)
    if html:
        import re
        return re.sub(r"<[^>]+>", " ", " ".join(html))
    return ""


@mcp.tool()
def get_profile() -> dict:
    """Return the address of the mailbox this server reads. Used as a health check."""
    p = gmail_get("profile")
    return {"email": p.get("emailAddress", ""), "messages_total": p.get("messagesTotal", 0)}


@mcp.tool()
def list_new_messages(after_epoch_seconds: int, max_results: int = 50) -> list[dict]:
    """List message ids received after the given Unix time (seconds), newest first. Inbox only, no spam or trash."""
    params = {"q": f"after:{int(after_epoch_seconds)} in:inbox", "maxResults": max(1, min(int(max_results), 100))}
    data = gmail_get("messages", params)
    return [{"id": m["id"], "thread_id": m.get("threadId", "")} for m in data.get("messages", [])]


@mcp.tool()
def get_message(message_id: str) -> dict:
    """Return one message: sender, subject, date, snippet, plain-text body and the two newsletter signals."""
    m = gmail_get(f"messages/{message_id}", {"format": "full"})
    payload = m.get("payload", {}) or {}
    headers = payload.get("headers", []) or []
    return {
        "id": m.get("id", message_id),
        "thread_id": m.get("threadId", ""),
        "sender": _header(headers, "From"),
        "to": _header(headers, "To"),
        "subject": _header(headers, "Subject"),
        "date": _header(headers, "Date"),
        "internal_date_ms": int(m.get("internalDate", 0) or 0),
        "snippet": m.get("snippet", ""),
        "body": _text_of(payload),
        "list_unsubscribe": bool(_header(headers, "List-Unsubscribe")),
        "precedence_bulk": _header(headers, "Precedence").lower() in ("bulk", "list", "junk"),
        "labels": m.get("labelIds", []),
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
