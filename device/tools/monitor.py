"""Live monitor for the agent: what was recorded, sent, queued, parked, dead, or missing.

Read-only. It reads device/state/<meter>_events.jsonl, the outbox and the meter counter.

    .\\.venv\\Scripts\\python.exe -m device.tools.monitor --meter M-07        # then open http://127.0.0.1:8765
"""
import argparse
import json
import os
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from device.agent.eventlog import EventLog
from device.tools.feedwatch import FeedWatcher

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
.matched{outline:3px solid #00acc1;outline-offset:1px}
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
 <div class="card">matched by B<b id="matchedCount">-</b></div>
</div>
<h3 style="font-size:14px">every window, by sequence number</h3>
<div class="grid" id="grid"></div>
<p style="font-size:12px">green = acked by B · amber = queued · purple = parked · red = dead · black = made but no ack and not queued (MISSING) · grey = made, status not yet known</p>
<h3 style="font-size:14px">B's feed: accepted matches</h3>
<div class="row">
 <div class="card">accepted<b id="acc">-</b></div>
 <div class="card">rejected<b id="rej">-</b></div>
 <div class="card">feed<b id="feed">-</b></div>
</div>
<table><thead><tr><th>time (A)</th><th>song</th><th>position in song</th><th>score</th><th>result</th></tr></thead><tbody id="matches"></tbody></table>
<h3 style="font-size:14px">recent events</h3>
<table><thead><tr><th>time</th><th>event</th><th>seq</th><th>detail</th></tr></thead><tbody id="events"></tbody></table>
<script>
async function refresh(){
  const s = await (await fetch('/api/state')).json();
  document.getElementById('meter').textContent = s.meter;
  for (const k of ['made','acked','queued','parked','dead','missing']) document.getElementById(k).textContent = s[k];
  const n = document.getElementById('net'); n.textContent = s.network; n.className = 'net-' + s.network;
  const g = document.getElementById('grid'); g.innerHTML = '';
  for (const q of s.seqs){ const d = document.createElement('div'); d.className = 'sq ' + q.status + (q.match==='accepted' ? ' matched' : ''); d.textContent = q.seq; d.title = 'seq '+q.seq+': sent '+q.status+' · match '+q.match+(q.song ? ' ('+q.song+')' : ''); g.appendChild(d); }
  document.getElementById('matchedCount').textContent = s.seqs.filter(q => q.match==='accepted').length;
  const tb = document.getElementById('events'); tb.innerHTML = '';
  for (const e of s.events.slice(-40).reverse()){
    const tr = document.createElement('tr');
    const detail = e.event === 'window' ? ('peaks '+e.peaks+'  loudness '+e.loudness_db+' dBFS') :
                   (e.event === 'network' ? (e.state+' '+(e.error||'')) : (e.status||e.reason||e.error||''));
    tr.innerHTML = '<td>'+e.t.slice(11,23)+'</td><td>'+e.event+'</td><td>'+(e.seq??'')+'</td><td>'+detail+'</td>';
    tb.appendChild(tr);
  }
}
async function refreshMatches(){
  const s = await (await fetch('/api/state')).json();
  document.getElementById('acc').textContent = s.matches.accepted;
  document.getElementById('rej').textContent = s.matches.rejected;
  const f = document.getElementById('feed');
  f.textContent = s.feed.connected ? 'connected' : ('down' + (s.feed.error ? ' ('+s.feed.error+')' : ''));
  const tb = document.getElementById('matches'); tb.innerHTML = '';
  for (const m of s.matches.recent.slice(0, 40)){
    const tr = document.createElement('tr');
    const pos = m.offset_s == null ? '' : (Number(m.offset_s).toFixed(1) + ' s');
    tr.innerHTML = '<td>'+m.t.slice(11,19)+'</td><td>'+(m.title||'-')+'</td><td>'+pos+'</td><td>'+(m.confidence??'')+'</td><td>'+(m.accepted?'<b style="color:#2e7d32">accepted</b>':'rejected')+'</td>';
    tb.appendChild(tr);
  }
}
refresh(); refreshMatches(); setInterval(refresh, 1500); setInterval(refreshMatches, 1500);
</script></body></html>"""


def read_matches(meter: str, state_dir: str = STATE_DIR, limit: int = 300) -> dict:
    path = os.path.join(state_dir, f"{meter}_feed.jsonl")
    if not os.path.exists(path):
        return {"accepted": 0, "rejected": 0, "recent": []}
    with open(path, "r", encoding="utf-8") as fh:
        recs = []
        for line in fh.readlines()[-5000:]:
            try:
                recs.append(json.loads(line))
            except ValueError:
                continue
    matches = [r for r in recs if r.get("kind") == "match" and r.get("meter_id") == meter]
    accepted = [r for r in matches if r.get("accepted")]
    by_window = {}
    for r in matches:  # the same window_start links a match back to the batch (seq) sent by the agent
        by_window[r.get("window_start")] = r
    return {
        "accepted": len(accepted),
        "rejected": len(matches) - len(accepted),
        "recent": matches[-limit:][::-1],
        "by_window": by_window,
    }


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
    matches = read_matches(meter, state_dir)
    by_window = matches.pop("by_window", {})
    window_of = {s: e.get("window_start") for s, e in made.items()}
    for q in seqs:
        m = by_window.get(window_of.get(q["seq"]))
        if m is None:
            q["match"], q["song"] = "none", None
        elif m.get("accepted"):
            q["match"], q["song"] = "accepted", m.get("title") or m.get("song_id")
        else:
            q["match"], q["song"] = "rejected", None
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
        "matches": matches,
        "feed": FEED_STATUS,
    }


def _sync_feed_status(watcher: FeedWatcher) -> None:
    """Copy the watcher's status into FEED_STATUS every second, for the page."""
    def loop():
        import time
        while True:
            FEED_STATUS["connected"] = watcher.connected
            FEED_STATUS["error"] = watcher.last_error
            time.sleep(1)
    threading.Thread(target=loop, daemon=True).start()


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


FEED_STATUS = {"connected": False, "error": None, "url": None}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="agent monitor (read-only; watches B's feed)")
    p.add_argument("--meter", default="M-07")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--sonacam", default="http://192.168.1.51:8000", help="B's base URL for the live feed")
    args = p.parse_args(argv)
    watcher = FeedWatcher(args.sonacam, os.path.join(STATE_DIR, f"{args.meter}_feed.jsonl"))
    watcher.start()
    FEED_STATUS["url"] = watcher.url
    _sync_feed_status(watcher)
    server = HTTPServer(("127.0.0.1", args.port), make_handler(args.meter, STATE_DIR))
    print(f"monitor for {args.meter}: http://127.0.0.1:{args.port}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
