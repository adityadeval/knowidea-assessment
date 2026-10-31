"""The agent: two tasks in one process.

  telegram_loop  long-polls Telegram, drops every chat but the allowed one, answers commands.
  check_loop     every CHECK_INTERVAL_SECONDS reads new email through the MCP server and decides.

    python -m agent.main
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone

from agent import logbook
from agent.config import require, settings
from agent.decide import ModelDecider
from agent.gmail_client import gmail_session
from agent.rules import Decision, Email, decide_by_rules, load_rules
from agent.store import Store, iso, now_utc
from agent.telegram import Telegram, parse_command

HELP = (
    "I watch your inbox and tell you when an email needs you.\n"
    "Commands: hello, What is new?, mute 2h, unmute.\n"
    "I only read email. I cannot send, delete or change anything."
)
REFUSAL = "I only read email. I cannot delete, send, reply to, move or change any message."


def format_alert(email: Email, d: Decision) -> str:
    by = "rule" if d.by == "rule" else "model"
    return (
        "Needs attention\n"
        f"From: {email.sender}\n"
        f"Subject: {email.subject or '(no subject)'}\n"
        f"Why: {d.reason}\n"
        f"(decided by {by})"
    )


def format_whats_new(store: Store) -> str:
    alerts = store.alerts_since(24)
    if not alerts:
        return "Nothing needed your attention in the last 24 hours."
    lines = [f"{len(alerts)} alert(s) in the last 24 hours:"]
    for i, a in enumerate(alerts, 1):
        when = a.alerted_at[11:16] + " UTC"
        lines.append(f"{i}. [{when}] {a.sender}\n   {a.subject or '(no subject)'}\n   {a.reason}")
    return "\n".join(lines)


class Agent:
    def __init__(self):
        self.s = settings()
        self.store = Store(self.s.db_path)
        self.tg = Telegram(self.s.telegram_bot_token, self.s.telegram_chat_id)
        self.model = ModelDecider(self.s.anthropic_api_key, self.s.llm_model)

    # --- email side ---------------------------------------------------------------------------------
    def muted(self) -> bool:
        until = self.store.get_meta("mute_until")
        return bool(until) and until > iso(now_utc())

    async def decide(self, email: Email, rules) -> Decision | None:
        return decide_by_rules(email, rules) or await self.model.decide(email, rules)

    async def check_once(self) -> None:
        rules = load_rules(self.s.rules_path)
        last = self.store.get_meta("last_check_at")
        since = datetime.fromisoformat(last) if last else now_utc() - timedelta(seconds=self.s.check_interval_seconds)
        since -= timedelta(minutes=2)  # overlap on purpose; the handled table removes the duplicates
        new_count = alert_count = 0
        try:
            async with gmail_session() as gmail:
                for ref in await gmail.list_new(int(since.timestamp())):
                    if self.store.is_handled(ref["id"]):
                        continue
                    new_count += 1
                    email = await gmail.get(ref["id"])
                    d = await self.decide(email, rules)
                    if d is None:
                        self.store.record_decision(email.id, "undecided", "model gave no usable verdict", "none",
                                                   email.sender, email.subject, alerted=False)
                        logbook.log_decision(email.id, "undecided", "none", email.sender, email.subject,
                                             "model gave no usable verdict; will retry")
                        continue
                    alerted = False
                    if d.decision == "alert":
                        if self.muted():
                            logbook.log_event(f"muted: alert for {email.id} not sent")
                        else:
                            await self.tg.send(format_alert(email, d))
                            alerted = True
                            alert_count += 1
                    self.store.record_decision(email.id, d.decision, d.reason, d.by, email.sender, email.subject, alerted)
                    logbook.log_decision(email.id, d.decision, d.by, email.sender, email.subject, d.reason)
        except Exception as e:  # one bad check must not kill the loop
            logbook.log_event(f"check failed: {type(e).__name__}: {e}")
        self.store.record_check(new_count, alert_count)
        logbook.log_check(new_count, alert_count)

    async def check_loop(self) -> None:
        interval = self.s.check_interval_seconds
        next_run = time.monotonic()
        while True:
            await self.check_once()
            next_run += interval                      # fixed cadence: no drift from the check's own duration
            await asyncio.sleep(max(0.0, next_run - time.monotonic()))

    # --- telegram side ------------------------------------------------------------------------------
    async def handle(self, text: str) -> str:
        cmd, minutes = parse_command(text)
        if cmd == "hello":
            return "Hello. I am watching your inbox and will message you when an email needs you."
        if cmd == "whats_new":
            return format_whats_new(self.store)
        if cmd == "mute":
            until = now_utc() + timedelta(minutes=minutes or 60)
            self.store.set_meta("mute_until", iso(until))
            logbook.log_event(f"muted until {iso(until)}")
            return f"Muted for {minutes} minutes, until {until.strftime('%H:%M')} UTC. Decisions are still logged."
        if cmd == "unmute":
            self.store.set_meta("mute_until", "")
            return "Alerts are on again."
        if cmd == "write_request":
            return REFUSAL
        return HELP

    async def telegram_loop(self) -> None:
        offset = None
        while True:
            try:
                for msg in await self.tg.poll(offset):
                    offset = msg.update_id + 1
                    if not self.tg.is_allowed(msg):
                        logbook.log_event(f"dropped message from chat {msg.chat_id}")
                        continue
                    await self.tg.send(await self.handle(msg.text))
            except Exception as e:
                logbook.log_event(f"telegram poll failed: {type(e).__name__}: {e}")
                await asyncio.sleep(5)

    async def run(self) -> None:
        logbook.log_event(f"agent started; model={self.s.llm_model}; interval={self.s.check_interval_seconds}s")
        try:
            await asyncio.gather(self.telegram_loop(), self.check_loop())
        finally:
            await self.tg.close()
            self.store.close()


def main() -> None:
    s = settings()
    logbook.setup(s.log_path)
    missing = require(s)
    if missing:
        raise SystemExit("cannot start, missing: " + ", ".join(missing))
    asyncio.run(Agent().run())


if __name__ == "__main__":
    main()
