"""Acceptance test 11: run the decision pipeline on real emails the user has labelled.

Two steps:
  python -m eval.run_eval collect 50     # read the latest 50 inbox emails through the MCP server -> eval/emails.jsonl
                                         # set GMAIL_TOKEN_FILE=token-other.json to read a different mailbox
  (the user fills "label" with alert or ignore in that file)
  python -m eval.run_eval score          # decide each one (rules first, model second), print the confusion matrix

Targets from the document: at least 90% of the emails labelled alert cause an alert; at most 5 of 50 cause a false alert.
Nothing is sent to Telegram and nothing is written to the state file: this is a dry run of decide().
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

from agent.config import settings
from agent.decide import ModelDecider
from agent.gmail_client import gmail_session
from agent.rules import Email, decide_by_rules, load_rules

HERE = Path(__file__).resolve().parent
DATA = HERE / "emails.jsonl"


async def collect(n: int) -> None:
    rows = []
    async with gmail_session() as gmail:
        refs = await gmail.list_new(after_epoch_seconds=int(time.time()) - 400 * 86400, max_results=n)
        for ref in refs:
            e = await gmail.get(ref["id"])
            rows.append({
                "id": e.id, "sender": e.sender, "subject": e.subject, "snippet": e.snippet,
                "body": e.body[:3000], "list_unsubscribe": e.list_unsubscribe, "precedence_bulk": e.precedence_bulk,
                "received_at": e.received_at, "label": "",
            })
    with DATA.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"wrote {len(rows)} emails to {DATA}. Fill 'label' with alert or ignore, then run: score")


async def score() -> None:
    s = settings()
    rules = load_rules(s.rules_path)
    model = ModelDecider(s.anthropic_api_key, s.llm_model)
    rows = [json.loads(line) for line in DATA.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows = [r for r in rows if r.get("label") in ("alert", "ignore")]
    if not rows:
        raise SystemExit("no labelled rows in eval/emails.jsonl")
    tp = fp = fn = tn = undecided = by_rule = 0
    results = []
    for r in rows:
        e = Email(id=r["id"], sender=r["sender"], subject=r["subject"], body=r.get("body", ""), snippet=r.get("snippet", ""),
                  list_unsubscribe=r.get("list_unsubscribe", False), precedence_bulk=r.get("precedence_bulk", False),
                  received_at=r.get("received_at", ""))
        d = decide_by_rules(e, rules)
        if d:
            by_rule += 1
        else:
            d = await model.decide(e, rules)
        got = d.decision if d else "undecided"
        want = r["label"]
        if got == "undecided":
            undecided += 1
            if want == "alert":
                fn += 1          # an undecided email never alerts, so for recall it counts as a miss
            else:
                tn += 1
        elif got == "alert" and want == "alert":
            tp += 1
        elif got == "alert" and want == "ignore":
            fp += 1
        elif got == "ignore" and want == "alert":
            fn += 1
        else:
            tn += 1
        mark = "ok " if got == want else "MISS" if want == "alert" else "FALSE"
        if got == "undecided":
            mark = "UND "
        results.append({"id": r["id"], "want": want, "got": got, "by": d.by if d else "none",
                        "reason": d.reason if d else "", "sender": r["sender"], "subject": r["subject"]})
        print(f"{mark} want={want:6} got={got:9} by={d.by if d else 'none':5} | {r['sender'][:30]:30} | {r['subject'][:50]}")
    n_alert = tp + fn
    recall = (tp / n_alert * 100) if n_alert else 0.0
    print("\n==== test 11 ====")
    print(f"emails: {len(rows)}   labelled alert: {n_alert}   labelled ignore: {fp + tn}")
    print(f"true alerts: {tp}   missed alerts: {fn}   false alerts: {fp}   correct ignores: {tn}   undecided: {undecided}")
    print(f"decided by rules without a model call: {by_rule}/{len(rows)}")
    print(f"recall on 'alert' = {recall:.0f}% (target >= 90%)   false alerts = {fp} (target <= 5 of 50)")
    print("PASS" if recall >= 90 and fp <= 5 else "FAIL")
    (HERE / "results.jsonl").write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in results) + "\n", encoding="utf-8")
    print(f"per-email results written to {HERE / 'results.jsonl'}")


def main() -> None:
    if len(sys.argv) >= 2 and sys.argv[1] == "collect":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 50
        asyncio.run(collect(n))
    elif len(sys.argv) >= 2 and sys.argv[1] == "score":
        asyncio.run(score())
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
