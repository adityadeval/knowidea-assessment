"""Print what is in state.db: recent decisions and recent check runs. Read-only.

    python -m tools.show_state
"""
from __future__ import annotations

import sqlite3

from agent.config import settings


def main() -> None:
    conn = sqlite3.connect(f"file:{settings().db_path}?mode=ro", uri=True)
    print("== handled (latest 20) ==")
    for r in conn.execute("SELECT decided_at, decision, decided_by, sender, subject, alerted_at FROM handled "
                          "ORDER BY decided_at DESC LIMIT 20"):
        print(f"{r[0]}  {r[1]:9} by={r[2]:5} alerted={'yes' if r[5] else 'no ':3}  {r[3][:35]:35}  {r[4][:50]}")
    print("\n== checks (latest 10) ==")
    for r in conn.execute("SELECT run_at, new_count, alert_count FROM checks ORDER BY run_at DESC LIMIT 10"):
        print(f"{r[0]}  new={r[1]}  alerts={r[2]}")
    print("\n== meta ==")
    for r in conn.execute("SELECT key, value FROM meta"):
        print(f"{r[0]} = {r[1]}")


if __name__ == "__main__":
    main()
