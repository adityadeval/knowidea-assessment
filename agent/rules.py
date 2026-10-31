"""The rules file and the deterministic decisions made from it. Pure functions: no I/O except load_rules.

Order of the checks in decide_by_rules (first match wins):
  1. sender in ignore_senders                      -> ignore
  2. important sender AND an alert keyword          -> alert
  3. newsletter headers or an ignore keyword        -> ignore
  4. nothing matched                                -> None (the model decides)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class Rules:
    important_senders: list[str] = field(default_factory=list)
    alert_keywords: list[str] = field(default_factory=list)
    ignore_senders: list[str] = field(default_factory=list)
    ignore_keywords: list[str] = field(default_factory=list)
    attention_guidance: str = ""


@dataclass
class Email:
    id: str
    sender: str            # the From header, e.g. 'Jane Doe <jane@acme.com>'
    subject: str
    body: str              # plain text, may be empty
    snippet: str = ""
    list_unsubscribe: bool = False
    precedence_bulk: bool = False
    received_at: str = ""  # ISO 8601, informational


@dataclass
class Decision:
    decision: str   # alert | ignore
    reason: str     # one sentence shown to the user
    by: str         # rule | model


def load_rules(path: Path) -> Rules:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return Rules(
        important_senders=[str(x).lower() for x in data.get("important_senders") or []],
        alert_keywords=[str(x).lower() for x in data.get("alert_keywords") or []],
        ignore_senders=[str(x).lower() for x in data.get("ignore_senders") or []],
        ignore_keywords=[str(x).lower() for x in data.get("ignore_keywords") or []],
        attention_guidance=str(data.get("attention_guidance") or "").strip(),
    )


def address_of(sender: str) -> str:
    """'Jane Doe <jane@acme.com>' -> 'jane@acme.com'; a bare address passes through."""
    s = sender.strip().lower()
    if "<" in s and s.endswith(">"):
        return s[s.rindex("<") + 1:-1].strip()
    return s


def sender_matches(patterns: list[str], sender: str) -> str | None:
    """Return the matching pattern. A pattern is a full address, a '@domain' suffix, or a 'local@' prefix."""
    addr = address_of(sender)
    for p in patterns:
        if p.startswith("@") and addr.endswith(p):
            return p
        if p.endswith("@") and addr.startswith(p):
            return p
        if p == addr:
            return p
    return None


def keyword_in(keywords: list[str], *texts: str) -> str | None:
    hay = " ".join(t.lower() for t in texts if t)
    for k in keywords:
        if k and k in hay:
            return k
    return None


def decide_by_rules(email: Email, rules: Rules) -> Decision | None:
    ignored = sender_matches(rules.ignore_senders, email.sender)
    if ignored:
        return Decision("ignore", f"Sender matches the ignore rule '{ignored}'.", "rule")

    important = sender_matches(rules.important_senders, email.sender)
    if important:
        word = keyword_in(rules.alert_keywords, email.subject, email.body)
        if word:
            return Decision("alert", f"From an important sender ({important}) and mentions '{word}'.", "rule")

    if email.list_unsubscribe or email.precedence_bulk:
        return Decision("ignore", "Bulk mail: it carries newsletter headers (List-Unsubscribe or Precedence: bulk).", "rule")

    word = keyword_in(rules.ignore_keywords, email.subject)
    if word:
        return Decision("ignore", f"Subject matches the ignore keyword '{word}'.", "rule")

    return None
