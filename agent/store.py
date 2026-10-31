"""The state file: one SQLite database with the handled email IDs, the alerts and the check runs.

Restart-safe by construction: an email ID is in `handled` or it is not, and nothing else decides whether an alert
goes out a second time.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS handled (
  email_id    TEXT PRIMARY KEY,
  decision    TEXT NOT NULL,            -- alert | ignore | undecided
  reason      TEXT NOT NULL,
  decided_by  TEXT NOT NULL,            -- rule | model | none
  sender      TEXT NOT NULL,
  subject     TEXT NOT NULL,
  decided_at  TEXT NOT NULL,            -- ISO 8601 UTC
  alerted_at  TEXT,                     -- set once the Telegram message was sent
  attempts    INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS checks (
  run_at      TEXT NOT NULL,
  new_count   INTEGER NOT NULL,
  alert_count INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""

MAX_ATTEMPTS = 3


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


@dataclass
class Alert:
    email_id: str
    sender: str
    subject: str
    reason: str
    decided_by: str
    alerted_at: str


class Store:
    def __init__(self, path: Path | str):
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    # --- handled emails -------------------------------------------------------------------------
    def is_handled(self, email_id: str) -> bool:
        """True when the email has a final decision, or was retried too often to try again."""
        row = self.conn.execute("SELECT decision, attempts FROM handled WHERE email_id = ?", (email_id,)).fetchone()
        if row is None:
            return False
        return row["decision"] != "undecided" or row["attempts"] >= MAX_ATTEMPTS

    def record_decision(self, email_id: str, decision: str, reason: str, decided_by: str,
                        sender: str, subject: str, alerted: bool) -> None:
        """Insert or replace the decision for one email. Alerts are recorded only after the message was sent."""
        prev = self.conn.execute("SELECT attempts FROM handled WHERE email_id = ?", (email_id,)).fetchone()
        attempts = (prev["attempts"] + 1) if prev else 1
        ts = iso(now_utc())
        self.conn.execute(
            "INSERT OR REPLACE INTO handled (email_id, decision, reason, decided_by, sender, subject, decided_at, alerted_at, attempts)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (email_id, decision, reason, decided_by, sender, subject, ts, ts if alerted else None, attempts),
        )
        self.conn.commit()

    def alerts_since(self, hours: int = 24) -> list[Alert]:
        cutoff = iso(now_utc() - timedelta(hours=hours))
        rows = self.conn.execute(
            "SELECT email_id, sender, subject, reason, decided_by, alerted_at FROM handled"
            " WHERE decision = 'alert' AND alerted_at IS NOT NULL AND alerted_at >= ? ORDER BY alerted_at DESC",
            (cutoff,),
        ).fetchall()
        return [Alert(**dict(r)) for r in rows]

    # --- check runs -----------------------------------------------------------------------------
    def record_check(self, new_count: int, alert_count: int) -> None:
        self.conn.execute("INSERT INTO checks (run_at, new_count, alert_count) VALUES (?, ?, ?)",
                          (iso(now_utc()), new_count, alert_count))
        self.set_meta("last_check_at", iso(now_utc()))
        self.conn.commit()

    # --- meta -----------------------------------------------------------------------------------
    def get_meta(self, key: str) -> str | None:
        row = self.conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def set_meta(self, key: str, value: str) -> None:
        self.conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value))
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
