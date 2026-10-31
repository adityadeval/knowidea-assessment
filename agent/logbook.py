"""The log file. Two kinds of line, both one line each, both timestamped in UTC:

  2026-10-31T18:00:01+00:00 CHECK new=3 alerts=1
  2026-10-31T18:00:02+00:00 DECISION id=18f3a2 decision=alert by=rule from="a@b.com" subject="Q3 deadline" reason="..."
"""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

LOG = logging.getLogger("agent")


class UtcFormatter(logging.Formatter):
    """Timestamps in UTC, ISO 8601, to the second."""
    converter = time.gmtime

    def __init__(self) -> None:
        super().__init__("%(asctime)s %(message)s", datefmt="%Y-%m-%dT%H:%M:%S+00:00")


def setup(log_path: Path) -> None:
    LOG.setLevel(logging.INFO)
    LOG.handlers.clear()
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(UtcFormatter())
    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setFormatter(UtcFormatter())
    LOG.addHandler(file_handler)
    LOG.addHandler(stream_handler)


def q(s: str) -> str:
    """One-line quoted field for the log: no newlines, no stray quotes."""
    return '"' + s.replace("\n", " ").replace('"', "'").strip() + '"'


def log_check(new_count: int, alert_count: int) -> None:
    LOG.info("CHECK new=%d alerts=%d", new_count, alert_count)


def log_decision(email_id: str, decision: str, by: str, sender: str, subject: str, reason: str) -> None:
    LOG.info("DECISION id=%s decision=%s by=%s from=%s subject=%s reason=%s",
             email_id, decision, by, q(sender), q(subject), q(reason))


def log_event(message: str) -> None:
    LOG.info("EVENT %s", message)
