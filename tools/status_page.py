"""A read-only status page for the running agent. Stretch beyond the document (version 1 is Telegram only).

    python -m tools.status_page          # then open http://localhost:8080

It reads state.db, decisions.log and rules.yaml and renders one HTML page that refreshes itself every 30 seconds.
It never writes anything and never talks to Telegram, Gmail or the model, so it cannot interfere with the agent.
Standard library only.
"""
from __future__ import annotations

import html
import sqlite3
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

from agent.config import settings

S = settings()

CSS = """
:root { --bg:#0f1117; --card:#171a23; --line:#262a36; --fg:#e8eaf0; --muted:#8b91a3; --ok:#3ddc97; --warn:#ffb454; --bad:#ff6b6b; --accent:#7aa2f7; }
* { box-sizing:border-box } body { margin:0; background:var(--bg); color:var(--fg); font:14px/1.5 -apple-system,Segoe UI,Inter,Roboto,sans-serif; }
.wrap { max-width:1100px; margin:0 auto; padding:28px 20px 60px }
h1 { font-size:22px; margin:0 0 4px; font-weight:600 } .sub { color:var(--muted); margin-bottom:22px }
.tiles { display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:12px; margin-bottom:22px }
.tile { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:14px 16px }
.tile .k { color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.04em } .tile .v { font-size:26px; font-weight:600; margin-top:2px }
.card { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:16px 18px; margin-bottom:16px }
.card h2 { font-size:14px; margin:0 0 10px; color:var(--muted); text-transform:uppercase; letter-spacing:.04em; font-weight:600 }
table { width:100%; border-collapse:collapse } th { text-align:left; color:var(--muted); font-weight:500; font-size:12px; padding:6px 8px; border-bottom:1px solid var(--line) }
td { padding:7px 8px; border-bottom:1px solid var(--line); vertical-align:top } tr:last-child td { border-bottom:0 }
.pill { display:inline-block; padding:1px 8px; border-radius:999px; font-size:12px; font-weight:600 }
.alert { background:rgba(255,107,107,.15); color:var(--bad) } .ignore { background:rgba(61,220,151,.15); color:var(--ok) } .undecided { background:rgba(255,180,84,.15); color:var(--warn) }
.by { color:var(--muted); font-size:12px } .mono { font-family:ui-monospace,Consolas,monospace; font-size:12px; white-space:pre-wrap; color:#c9cdd8 }
.status { display:flex; gap:18px; flex-wrap:wrap; color:var(--muted) } .status b { color:var(--fg); font-weight:600 } #cd { color:var(--accent); font-variant-numeric:tabular-nums }
.dot { display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:6px; background:var(--ok) } .dot.off { background:var(--bad) }
"""


def esc(x) -> str:
    return html.escape(str(x if x is not None else ""))


def pill(decision: str) -> str:
    return f'<span class="pill {esc(decision)}">{esc(decision)}</span>'


def when(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).astimezone().strftime("%I:%M %p").lstrip("0")
    except Exception:
        return iso or ""


def render() -> str:
    conn = sqlite3.connect(f"file:{S.db_path}?mode=ro", uri=True) if S.db_path.exists() else None
    now = datetime.now(timezone.utc)
    q = (lambda sql, *a: conn.execute(sql, a).fetchall()) if conn else (lambda sql, *a: [])
    one = lambda sql, *a: (q(sql, *a) or [[None]])[0][0]

    last_check = one("SELECT value FROM meta WHERE key='last_check_at'")
    mute_until = one("SELECT value FROM meta WHERE key='mute_until'")
    alive = bool(last_check) and datetime.fromisoformat(last_check) > now - timedelta(seconds=S.check_interval_seconds + 120)
    next_check = (datetime.fromisoformat(last_check) + timedelta(seconds=S.check_interval_seconds)) if last_check else None
    muted = bool(mute_until) and mute_until > now.isoformat()

    checks = one("SELECT COUNT(*) FROM checks") or 0
    seen = one("SELECT COUNT(*) FROM handled") or 0
    alerts_sent = one("SELECT COUNT(*) FROM handled WHERE alerted_at IS NOT NULL") or 0
    undecided = one("SELECT COUNT(*) FROM handled WHERE decision='undecided'") or 0

    cutoff = (now - timedelta(hours=24)).isoformat()
    alerts = q("SELECT alerted_at, sender, subject, reason, decided_by FROM handled WHERE alerted_at IS NOT NULL AND alerted_at >= ? ORDER BY alerted_at DESC", cutoff)
    decisions = q("SELECT decided_at, decision, decided_by, sender, subject, reason FROM handled ORDER BY decided_at DESC LIMIT 30")
    runs = q("SELECT run_at, new_count, alert_count FROM checks ORDER BY run_at DESC LIMIT 12")
    rules_text = S.rules_path.read_text(encoding="utf-8") if S.rules_path.exists() else "(no rules.yaml)"
    log_tail = "\n".join(S.log_path.read_text(encoding="utf-8").splitlines()[-25:]) if S.log_path.exists() else "(no log yet)"

    rows_alerts = "".join(
        f"<tr><td>{when(a[0])}</td><td>{esc(a[1])}</td><td>{esc(a[2])}</td><td>{esc(a[3])} <span class='by'>({esc(a[4])})</span></td></tr>"
        for a in alerts) or "<tr><td colspan=4 class='by'>Nothing needed your attention in the last 24 hours.</td></tr>"
    rows_dec = "".join(
        f"<tr><td>{when(d[0])}</td><td>{pill(d[1])}</td><td class='by'>{esc(d[2])}</td><td>{esc(d[3])}</td><td>{esc(d[4])}</td><td>{esc(d[5])}</td></tr>"
        for d in decisions) or "<tr><td colspan=6 class='by'>No decisions yet.</td></tr>"
    rows_runs = "".join(f"<tr><td>{when(r[0])}</td><td>{r[1]}</td><td>{r[2]}</td></tr>" for r in runs) or "<tr><td colspan=3 class='by'>No checks yet.</td></tr>"

    return f"""<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="refresh" content="30">
<title>Chief of Staff Agent</title><style>{CSS}</style></head><body><div class="wrap">
<h1>Chief of Staff Agent</h1><div class="sub">Read-only view of the running agent. Refreshes every 30 s. Version 1 interface is the Telegram chat; this page only watches.</div>
<div class="card"><div class="status">
<span><span class="dot {'' if alive else 'off'}"></span>{'Running' if alive else 'No recent check'}</span>
<span>Last check <b>{when(last_check) if last_check else '—'}</b></span>
<span>Next check <b>{when(next_check.isoformat()) if next_check else '—'}</b></span>
<span>Countdown <b id="cd" data-next="{int(next_check.timestamp()) if next_check else 0}">—</b></span>
<span>Interval <b>{S.check_interval_seconds // 60} min</b></span>
<span>Alerts <b>{'muted until ' + when(mute_until) if muted else 'on'}</b></span>
<span>Model <b>{esc(S.llm_model)}</b></span>
</div></div>
<div class="tiles">
<div class="tile"><div class="k">Checks run</div><div class="v">{checks}</div></div>
<div class="tile"><div class="k">Emails seen</div><div class="v">{seen}</div></div>
<div class="tile"><div class="k">Alerts sent</div><div class="v">{alerts_sent}</div></div>
<div class="tile"><div class="k">Undecided</div><div class="v">{undecided}</div></div>
</div>
<div class="card"><h2>Alerts, last 24 hours</h2><table><tr><th>When</th><th>From</th><th>Subject</th><th>Why</th></tr>{rows_alerts}</table></div>
<div class="card"><h2>Latest decisions</h2><table><tr><th>When</th><th>Decision</th><th>By</th><th>From</th><th>Subject</th><th>Reason</th></tr>{rows_dec}</table></div>
<div class="card"><h2>Check runs</h2><table><tr><th>When</th><th>New emails</th><th>Alerts</th></tr>{rows_runs}</table></div>
<div class="card"><h2>Rules file (rules.yaml, edit it in any editor)</h2><div class="mono">{esc(rules_text)}</div></div>
<div class="card"><h2>Log tail (decisions.log)</h2><div class="mono">{esc(log_tail)}</div></div>
</div>
<script>
(function(){{var el=document.getElementById('cd');var t=parseInt(el.dataset.next||'0',10);
function tick(){{if(!t){{el.textContent='—';return;}}var d=t-Math.floor(Date.now()/1000);
if(d<=0){{el.textContent='checking now…';return;}}var m=Math.floor(d/60),s=d%60;el.textContent=m+':'+(s<10?'0':'')+s+' until next check';}}
tick();setInterval(tick,1000);}})();
</script>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = render().encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # keep the agent's terminal quiet; this page has its own
        pass


def main(port: int = 8080) -> None:
    print(f"status page on http://localhost:{port}  (read-only; Ctrl+C to stop)")
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
