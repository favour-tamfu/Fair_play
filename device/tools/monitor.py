"""Live monitor for the agent: what was recorded, sent, queued, parked, dead, or missing.

Read-only. It reads device/state/<meter>_events.jsonl, the outbox and the meter counter.

    .\\.venv\\Scripts\\python.exe -m device.tools.monitor --meter M-07        # then open http://127.0.0.1:8765
"""
import argparse
import json
import os
import sqlite3
from http.server import BaseHTTPRequestHandler, HTTPServer

from device.agent.eventlog import EventLog

STATE_DIR = os.path.join("device", "state")

PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>agent monitor</title>
<style>
body{font-family:Segoe UI,Arial,sans-serif;margin:16px;background:#fafafa;color:#222}
h1{font-size:18px;margin:0 0 8px} .row{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:12px}
.card{background:#fff;border:1px solid #ddd;border-radius:6px;padding:8px 12px;min-width:120px}
.card b{display:block;font-size:20px} .grid{display:flex;flex-wrap:wrap;gap:3px;margin:8px 0}
.sq{width:22px;height:22px;border-radius:3px;font-size:9px;display:flex;align-items:center;justify-content:center;color:#fff}
.acked{background:#2e7d32}.queued{background:#e0a100}.parked{background:#6a1b9a}.dead{background:#c62828}
.missing{background:#000}.made{background:#9e9e9e}
table{border-collapse:collapse;font-size:12px;background:#fff} td,th{border-bottom:1px solid #eee;padding:3px 8px;text-align:left}
.bar{height:10px;background:#4caf50;display:inline-block}
.net-OK{color:#2e7d32}.net-RETRYING{color:#e0a100}.net-DOWN{color:#c62828}
</style></head><body>
<h1>agent monitor — <span id="meter"></span></h1>
<div class="row">
 <div class="card">made<b id="made">-</b></div>
 <div class="card">acked<b id="acked">-</b></div>
 <div class="card">queued<b id="queued">-</b></div>
 <div class="card">parked<b id="parked">-</b></div>
 <div class="card">dead<b id="dead">-</b></div>
 <div class="card">missing<b id="missing">-</b></div>
 <div class="card">network<b id="net">-</b></div>
</div>
<h3 style="font-size:14px">every window, by sequence number</h3>
<div class="grid" id="grid"></div>
<p style="font-size:12px">green = acked by B · amber = queued · purple = parked · red = dead · black = made but no ack and not queued (MISSING) · grey = made, status not yet known</p>
<h3 style="font-size:14px">recent events</h3>
<table><thead><tr><th>time</th><th>event</th><th>seq</th><th>detail</th></tr></thead><tbody id="events"></tbody></table>
<script>
async function refresh(){
  const s = await (await fetch('/api/state')).json();
  document.getElementById('meter').textContent = s.meter;
  for (const k of ['made','acked','queued','parked','dead','missing']) document.getElementById(k).textContent = s[k];
  const n = document.getElementById('net'); n.textContent = s.network; n.className = 'net-' + s.network;
  const g = document.getElementById('grid'); g.innerHTML = '';
  for (const q of s.seqs){ const d = document.createElement('div'); d.className = 'sq ' + q.status; d.textContent = q.seq; d.title = 'seq '+q.seq+': '+q.status; g.appendChild(d); }
  const tb = document.getElementById('events'); tb.innerHTML = '';
  for (const e of s.events.slice(-40).reverse()){
    const tr = document.createElement('tr');
    const detail = e.event === 'window' ? ('peaks '+e.peaks+'  loudness '+e.loudness_db+' dBFS') :
                   (e.event === 'network' ? (e.state+' '+(e.error||'')) : (e.status||e.reason||e.error||''));
    tr.innerHTML = '<td>'+e.t.slice(11,23)+'</td><td>'+e.event+'</td><td>'+(e.seq??'')+'</td><td>'+detail+'</td>';
    tb.appendChild(tr);
  }
}
refresh(); setInterval(refresh, 1500);
</script></body></html>"""


def build_state(meter: str, state_dir: str = STATE_DIR) -> dict:
    events = EventLog(os.path.join(state_dir, f"{meter}_events.jsonl")).read()
    made, acked, parked, dead = {}, set(), set(), set()
    network = "OK"
    net_t, ack_t = "", ""
    for e in events:
        ev = e.get("event")
        if ev == "window":
            made[e["seq"]] = e
        elif ev == "acked":
            acked.add(e["seq"])
            ack_t = e.get("t", ack_t)
        elif ev == "parked":
            parked.add(e["seq"])
        elif ev == "dead":
            dead.add(e["seq"])
        elif ev == "network":
            network = e.get("state", network)
            net_t = e.get("t", net_t)
    # a server answer after the last network failure means the link is back, even if no OK event was written
    if network != "OK" and ack_t > net_t:
        network = "OK"
    queued = set()
    outbox_path = os.path.join(state_dir, f"{meter}_outbox.db")
    if os.path.exists(outbox_path):
        with sqlite3.connect(outbox_path) as con:
            queued = {r[0] for r in con.execute("SELECT seq FROM outbox")}
    last_made = max(made) if made else 0
    lo = min(made) if made else 0
    seqs = []
    for s in range(lo, last_made + 1):
        if s in acked:
            status = "acked"
        elif s in dead:
            status = "dead"
        elif s in queued:
            status = "queued"
        elif s in parked:
            status = "parked"
        elif s in made:
            status = "missing"   # made, never acked, not in the outbox: a real problem
        else:
            status = "made"
        seqs.append({"seq": s, "status": status})
    count = lambda k: sum(1 for q in seqs if q["status"] == k)  # noqa: E731
    return {
        "meter": meter,
        "made": len(made),
        "acked": len(acked),
        "queued": len(queued),
        "parked": len(parked),
        "dead": len(dead),
        "missing": count("missing"),
        "network": network,
        "seqs": seqs[-400:],
        "events": events[-200:],
    }


def make_handler(meter: str, state_dir: str):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            if self.path.startswith("/api/state"):
                body = json.dumps(build_state(meter, state_dir), ensure_ascii=False).encode("utf-8")
                ctype = "application/json"
            else:
                body = PAGE.encode("utf-8")
                ctype = "text/html; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):  # keep the console quiet
            pass

    return Handler


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="agent monitor (read-only)")
    p.add_argument("--meter", default="M-07")
    p.add_argument("--port", type=int, default=8765)
    args = p.parse_args(argv)
    server = HTTPServer(("127.0.0.1", args.port), make_handler(args.meter, STATE_DIR))
    print(f"monitor for {args.meter}: http://127.0.0.1:{args.port}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
