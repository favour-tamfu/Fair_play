"""Restart test (B-T16): send a meter's song windows while every server container is restarted; prove that no
batch is lost, no play is doubled and the ledger stays intact.

    python -m server.tools.chaos run [--songs S-000034,S-000029,S-000037] [--windows 12] [--gap 1.0] [--no-chaos]

1. `make` (run for you inside the api container, which has ffmpeg): the songs are decoded at 48 kHz and cut into
   signed batches of the TEST meter M-90 (key in contract/fixtures), played back to back, ending about now.
2. the batches are posted one by one like a meter: on a connection error / 5xx the same batch is retried with
   backoff (1, 2, 4 … 8 s), exactly as A's outbox does.
3. during the send, each container is restarted in turn: worker_match, api, worker_play, scheduler, db.
4. wait until every stored batch is matched and the play logger is idle, then check:
   stored batches == sent (no loss), plays of M-90 in the window == one per song, in order, no duplicates,
   superseded corrections counted, ledger intact.
Test data: plays of the virtual meter M-90 at V-BUEA-CIMFEST (live period); the demo reset removes them.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

CONTAINER_OUT = "/app/media/chaos_batches.json"
HOST_OUT = Path(__file__).resolve().parents[2] / "media" / "chaos_batches.json"
RESTARTS = ["worker_match", "api", "worker_play", "scheduler", "db"]


# ------------------------------------------------------------------ make (inside the container)

def make(songs: list[str], n: int, seq_start: int, ago_min: int = 0) -> None:
    import numpy as np

    from server.api.songs import resolve_path
    from server.db import connect
    from server.tools.make_batches_from_wav import make_batches
    with connect() as c:
        paths = {r["song_id"]: r["file_path"] for r in c.execute("SELECT song_id, file_path FROM songs WHERE song_id = ANY(%s)",
                                                                  (songs,))}
    start = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(seconds=10 * n * len(songs) + 30, minutes=ago_min)
    out, plan = [], []
    for k, s in enumerate(songs):
        pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", str(resolve_path(paths[s])), "-ac", "1", "-ar", "48000",
                              "-f", "f32le", "-"], check=True, capture_output=True).stdout
        x = np.frombuffer(pcm, dtype=np.float32)
        t = start + timedelta(seconds=10 * n * k)
        out += make_batches(x, seq_start=seq_start + n * k, start=t, offset_s=30.0, n=n)
        plan.append({"song_id": s, "start": t.isoformat()})
    Path(CONTAINER_OUT).write_text(json.dumps({"plan": plan, "batches": out}), "utf-8")
    print(f"{len(out)} batches for {len(songs)} songs")


# ------------------------------------------------------------------ run (on the host)

def compose(*args: str) -> None:
    subprocess.run(["docker", "compose", *args], check=True, capture_output=True)


def post_like_a_meter(url: str, b: dict, log: list) -> str:
    import httpx
    delay = 1.0
    while True:
        try:
            r = httpx.post(url + "/v1/batches", json=b, timeout=10)
            if r.status_code == 200:
                return r.json()["status"]
            log.append(f"seq {b['seq']}: HTTP {r.status_code}")
        except httpx.HTTPError as e:
            log.append(f"seq {b['seq']}: {type(e).__name__}")
        time.sleep(delay)
        delay = min(8.0, delay * 2)


def wait_idle(seqs: list[int], timeout: float = 240) -> dict:
    from server.db import connect
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        try:
            with connect() as c:
                r = c.execute("""SELECT count(*) FILTER (WHERE NOT processed) AS unprocessed, count(*) AS stored,
                                        (SELECT count(*) FROM jobs WHERE kind IN ('match','play') AND status IN ('queued','running')) AS busy
                                 FROM raw_batches WHERE meter_id = 'M-90' AND seq = ANY(%s)""", (seqs,)).fetchone()
            if r["unprocessed"] == 0 and r["busy"] == 0 and r["stored"] == len(seqs):
                time.sleep(3)                                     # let the play logger finish its last pass
                return dict(r)
        except Exception:
            pass
        time.sleep(2)
    raise SystemExit("timeout: the pipeline did not drain")


def verify(plan: list[dict], seqs: list[int], t_from: datetime, t_to: datetime) -> dict:
    import httpx

    from server.db import connect
    with connect() as c:
        stored = c.execute("SELECT count(*) AS n, count(DISTINCT seq) AS d FROM raw_batches WHERE meter_id = 'M-90' AND seq = ANY(%s)",
                           (seqs,)).fetchone()
        plays = c.execute("""SELECT p.play_id, p.song_id, p.started_at,
                                    EXISTS (SELECT 1 FROM play_corrections x WHERE x.play_id = p.play_id
                                            AND x.reason = 'not_confirmed_on_recompute') AS superseded
                             FROM plays p WHERE p.meter_id = 'M-90' AND p.chain = 'live'
                               AND p.started_at BETWEEN %s AND %s ORDER BY p.started_at""", (t_from, t_to)).fetchall()
        errors = c.execute("SELECT count(*) AS n FROM jobs WHERE kind IN ('match','play') AND status = 'error' "
                           "AND updated_at > now() - interval '30 minutes'").fetchone()["n"]
    active = [p for p in plays if not p["superseded"]]
    ledger = httpx.get("http://localhost:8000/api/v1/ledger/status", timeout=10).json()
    checks = {
        "no batch lost": stored["n"] == len(seqs),
        "no batch stored twice": stored["d"] == stored["n"],
        "one play per song, in order": [p["song_id"] for p in active] == [s["song_id"] for s in plan],
        "no job errors": errors == 0,
        "ledger intact": ledger["intact"],
    }
    return {"checks": checks, "stored": stored["n"], "sent": len(seqs),
            "plays": [(p["play_id"], p["song_id"], p["started_at"].isoformat(), p["superseded"]) for p in plays],
            "job_errors": errors, "ledger_plays_checked": ledger["plays_checked"]}


def run(a) -> int:
    seq_start = int(time.time()) % 1_000_000_000
    songs = a.songs.split(",")
    compose("exec", "-T", "api", "python", "-m", "server.tools.chaos", "make", "--songs", a.songs,
            "--windows", str(a.windows), "--seq-start", str(seq_start), "--ago", str(a.ago))
    data = json.loads(HOST_OUT.read_text("utf-8"))
    batches, plan = data["batches"], data["plan"]
    seqs = [b["seq"] for b in batches]
    t_from = datetime.fromisoformat(plan[0]["start"]) - timedelta(minutes=2)
    t_to = datetime.fromisoformat(plan[-1]["start"]) + timedelta(minutes=5)
    events, retries, answers = [], [], {}
    every = max(1, len(batches) // (len(RESTARTS) + 1))
    t0 = time.monotonic()
    for i, b in enumerate(batches):
        if not a.no_chaos and i and i % every == 0 and i // every <= len(RESTARTS):
            svc = RESTARTS[i // every - 1]
            threading.Thread(target=compose, args=("restart", svc), daemon=True).start()
            events.append(f"{time.monotonic() - t0:5.1f}s restart {svc} (before batch {i + 1})")
        st = post_like_a_meter(a.url, b, retries)
        answers[st] = answers.get(st, 0) + 1
        time.sleep(a.gap)
    print("\n".join(events) or "no restarts")
    print(f"sent {len(batches)} batches in {time.monotonic() - t0:.0f} s; answers {answers}; retries {len(retries)}")
    print("waiting for the pipeline to drain …")
    print(wait_idle(seqs))
    res = verify(plan, seqs, t_from, t_to)
    for p in res["plays"]:
        print("  play", p)
    for k, ok in res["checks"].items():
        print(f"  {'PASS' if ok else 'FAIL'}  {k}")
    print(json.dumps({k: v for k, v in res.items() if k not in ("checks", "plays")}))
    HOST_OUT.unlink(missing_ok=True)
    return 0 if all(res["checks"].values()) else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("make")
    m.add_argument("--songs", required=True)
    m.add_argument("--windows", type=int, default=12)
    m.add_argument("--seq-start", type=int, required=True)
    m.add_argument("--ago", type=int, default=0)
    r = sub.add_parser("run")
    r.add_argument("--songs", default="S-000034,S-000029,S-000037")
    r.add_argument("--windows", type=int, default=12)
    r.add_argument("--gap", type=float, default=1.0, help="seconds between batches")
    r.add_argument("--url", default="http://localhost:8000")
    r.add_argument("--no-chaos", action="store_true", help="baseline: no restarts")
    r.add_argument("--ago", type=int, default=0, help="song times this many minutes in the past (a backlog)")
    a = ap.parse_args(argv)
    if a.cmd == "make":
        make(a.songs.split(","), a.windows, a.seq_start, a.ago)
        return 0
    return run(a)


if __name__ == "__main__":
    sys.exit(main())
