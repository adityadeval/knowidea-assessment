"""Telegram Bot API over plain HTTPS (long polling). No webhook, no public URL.

Requirement 2 lives here: every update whose chat id is not the one allowed chat is dropped before any handler runs.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import httpx

API = "https://api.telegram.org/bot{token}/{method}"


@dataclass
class Incoming:
    update_id: int
    chat_id: int
    text: str


class Telegram:
    def __init__(self, token: str, allowed_chat_id: int):
        self.token = token
        self.allowed_chat_id = allowed_chat_id
        self.http = httpx.AsyncClient(timeout=httpx.Timeout(40.0, connect=10.0))

    async def call(self, method: str, **params) -> dict:
        r = await self.http.post(API.format(token=self.token, method=method), json=params)
        r.raise_for_status()
        data = r.json()
        if not data.get("ok"):
            raise RuntimeError(f"telegram {method}: {data}")
        return data["result"]

    async def send(self, text: str, chat_id: int | None = None) -> None:
        await self.call("sendMessage", chat_id=chat_id or self.allowed_chat_id, text=text,
                        disable_web_page_preview=True)

    async def poll(self, offset: int | None) -> list[Incoming]:
        """One long-poll round (up to 25 s). Returns only text messages, including ones from other chats:
        the caller applies the allowlist so that the drop is logged."""
        params = {"timeout": 25, "allowed_updates": ["message"]}
        if offset is not None:
            params["offset"] = offset
        updates = await self.call("getUpdates", **params)
        out = []
        for u in updates:
            msg = u.get("message") or {}
            text = msg.get("text")
            chat = (msg.get("chat") or {}).get("id")
            if text is None or chat is None:
                continue
            out.append(Incoming(update_id=u["update_id"], chat_id=int(chat), text=text))
        return out

    def is_allowed(self, incoming: Incoming) -> bool:
        return incoming.chat_id == self.allowed_chat_id

    async def close(self) -> None:
        await self.http.aclose()


# --- command parsing (pure) -----------------------------------------------------------------------
WRITE_WORDS = re.compile(r"\b(delete|remove|trash|archive|send|reply|forward|mark|move|label|star)\b", re.I)
MUTE = re.compile(r"^/?mute(?:\s+(\d+)\s*([hm]))?\s*$", re.I)


def normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", text.strip().lower()).strip()


def parse_command(text: str) -> tuple[str, int | None]:
    """Classify a user message. Returns (command, minutes) where command is one of
    hello | whats_new | mute | unmute | write_request | unknown and minutes is set for mute only."""
    norm = normalise(text)
    if norm in {"hello", "hi", "hey", "start", "hello there"} or text.strip().startswith("/start"):
        return "hello", None
    if norm in {"what is new", "whats new", "what is new today", "anything new", "news"}:
        return "whats_new", None
    if norm in {"unmute", "resume"}:
        return "unmute", None
    m = MUTE.match(text.strip())
    if m:
        if m.group(1) is None:
            return "mute", 60
        n, unit = int(m.group(1)), m.group(2).lower()
        return "mute", n * 60 if unit == "h" else n
    if WRITE_WORDS.search(text):
        return "write_request", None
    return "unknown", None
