"""Print the chat ids that have messaged the bot, so TELEGRAM_CHAT_ID can be filled in.

    python -m tools.chat_id

Send the bot any message first; then run this and copy the id of your own chat into .env.
"""
from __future__ import annotations

import httpx

from agent.config import settings


def main() -> None:
    s = settings()
    if not s.telegram_bot_token:
        raise SystemExit("TELEGRAM_BOT_TOKEN is empty in .env")
    r = httpx.get(f"https://api.telegram.org/bot{s.telegram_bot_token}/getUpdates", timeout=20)
    r.raise_for_status()
    seen = {}
    for u in r.json().get("result", []):
        msg = u.get("message") or {}
        chat = msg.get("chat") or {}
        if "id" in chat:
            who = chat.get("username") or f"{chat.get('first_name', '')} {chat.get('last_name', '')}".strip()
            seen[chat["id"]] = (who, msg.get("text", ""))
    if not seen:
        print("no messages yet: send the bot a message in Telegram, then run again")
    for cid, (who, text) in seen.items():
        print(f"chat_id={cid}  from={who!r}  last_text={text!r}")


if __name__ == "__main__":
    main()
