"""Play logger worker (B-T06, "the ledger clerk"): match verdicts → confirmed plays, by EVENT time.

Job "play", ref = meter_id. For each venue-night touched by new verdicts, the night is recomputed from ALL of that
meter's verdicts in window_start order (server/plays/segment.py) and reconciled with the plays already logged:
  - new confirmed play               → INSERT plays (hash-chained, immutable) + play_extents, NOTIFY "play"
  - same song overlapping a logged play → only play_extents changes (end, windows, duration, loudness);
                                       if its start moved by > 5 s a play_correction "started_at_changed" is written
  - logged play no longer confirmed   → play_correction "not_confirmed_on_recompute" (the original is never edited;
                                       stats skip superseded plays)
One path covers live, late (after a network cut, out of order) and restarted processing: re-running is idempotent.
Unidentified music is not recorded (D-011): an unmatched window is simply not a play.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import date, datetime, time, timedelta, timezone

import psycopg

from fairplay_core.schema import format_utc
from server import config
from server.db import notify
from server.ledger import chain
from server.plays.segment import Candidate, Event, segment

log = logging.getLogger("playlogger")
SUPERSEDED = "not_confirmed_on_recompute"
START_MOVED = "started_at_changed"


def venue_day(ws: datetime) -> date:
    """The venue-night a moment belongs to: local time minus VENUE_DAY_START_H hours (18:00–02:00 = one night)."""
    return (ws + timedelta(hours=config.LOCAL_UTC_OFFSET_H - config.VENUE_DAY_START_H)).date()


def day_bounds(d: date) -> tuple[datetime, datetime]:
    start = datetime.combine(d, time(config.VENUE_DAY_START_H), timezone.utc) - timedelta(hours=config.LOCAL_UTC_OFFSET_H)
    return start, start + timedelta(days=1)


def _correct_once(conn: psycopg.Connection, play_id: str, reason: str, detail: dict) -> bool:
    d = json.dumps(detail, sort_keys=True, default=str)
    if conn.execute("SELECT 1 FROM play_corrections WHERE play_id = %s AND reason = %s AND detail = %s::jsonb",
                    (play_id, reason, d)).fetchone():
        return False
    conn.execute("INSERT INTO play_corrections (play_id, reason, detail) VALUES (%s, %s, %s::jsonb)", (play_id, reason, d))
    log.warning("correction %s %s %s", play_id, reason, d)
    return True


def _insert_play(conn: psycopg.Connection, c: Candidate, meter: dict, d: date) -> str:
    play = {"play_id": f"P-{uuid.uuid4().hex[:12]}", "meter_id": meter["meter_id"], "venue_id": meter["venue_id"],
            "song_id": c.song_id, "started_at": c.started_at, "duration_s": round(c.duration_s, 1),
            "n_windows": c.n_windows}
    prev, h = chain.append(conn, play)
    conn.execute("""INSERT INTO plays (play_id, meter_id, venue_id, song_id, started_at, ended_at, duration_s, first_offset_s,
                                       n_windows, loudness_db, source, prev_chain_hash, chain_hash)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                 (play["play_id"], play["meter_id"], play["venue_id"], c.song_id, c.started_at, c.ended_at,
                  play["duration_s"], c.first_offset_s, c.n_windows, c.mean_loudness_db, meter["source"], prev, h))
    conn.execute("""INSERT INTO play_extents (play_id, ended_at, n_windows, duration_s, loudness_db, venue_day)
                    VALUES (%s,%s,%s,%s,%s,%s)""",
                 (play["play_id"], c.ended_at, c.n_windows, round(c.duration_s, 1), c.mean_loudness_db, d))
    song = conn.execute("SELECT title, artist_name FROM songs WHERE song_id = %s", (c.song_id,)).fetchone() or {}
    notify(conn, "play", {"play_id": play["play_id"], "venue_id": play["venue_id"], "song_id": c.song_id,
                          "title": song.get("title"), "artist_name": song.get("artist_name"),
                          "started_at": format_utc(c.started_at), "source": meter["source"]})
    log.info("PLAY %s %s %s started %s (%d windows)", play["play_id"], meter["meter_id"], c.song_id,
             format_utc(c.started_at), c.n_windows)
    return play["play_id"]


def rebuild_day(conn: psycopg.Connection, meter: dict, d: date) -> dict:
    lo, hi = day_bounds(d)
    rows = conn.execute("""SELECT id, window_start, accepted, song_id, offset_s, loudness_db FROM match_events
                           WHERE meter_id = %s AND window_start >= %s AND window_start < %s
                           ORDER BY window_start, id""", (meter["meter_id"], lo, hi)).fetchall()
    events = [Event(r["id"], r["window_start"], bool(r["accepted"]), r["song_id"], r["offset_s"] or 0.0,
                    r["loudness_db"]) for r in rows]
    lengths = {r["song_id"]: r["duration_s"] for r in conn.execute(
        "SELECT song_id, duration_s FROM songs WHERE song_id = ANY(%s)",
        (list({e.song_id for e in events if e.song_id}),))}
    confirmed = [c for c in segment(events, lambda s: lengths.get(s) or config.DEFAULT_SONG_LENGTH_S) if c.confirmed]

    existing = conn.execute(
        """SELECT p.play_id, p.song_id, p.started_at, x.ended_at FROM plays p JOIN play_extents x USING (play_id)
           WHERE p.chain = 'live' AND p.meter_id = %s AND x.venue_day = %s
             AND NOT EXISTS (SELECT 1 FROM play_corrections c WHERE c.play_id = p.play_id AND c.reason = %s)
           ORDER BY p.started_at""", (meter["meter_id"], d, SUPERSEDED)).fetchall()
    used: set[str] = set()
    inserted = updated = corrected = 0
    for c in confirmed:
        ex = next((p for p in existing if p["play_id"] not in used and p["song_id"] == c.song_id
                   and p["started_at"] < c.ended_at and c.started_at < p["ended_at"]), None)
        if ex is None:
            _insert_play(conn, c, meter, d)
            inserted += 1
            continue
        used.add(ex["play_id"])
        conn.execute("""UPDATE play_extents SET ended_at = %s, n_windows = %s, duration_s = %s, loudness_db = %s,
                        updated_at = now() WHERE play_id = %s""",
                     (c.ended_at, c.n_windows, round(c.duration_s, 1), c.mean_loudness_db, ex["play_id"]))
        updated += 1
        if abs((c.started_at - ex["started_at"]).total_seconds()) > config.SAME_PLAY_TOL_S:
            corrected += _correct_once(conn, ex["play_id"], START_MOVED, {"started_at": format_utc(c.started_at)})
    for p in existing:
        if p["play_id"] not in used:
            corrected += _correct_once(conn, p["play_id"], SUPERSEDED, {"venue_day": str(d)})

    return {"day": str(d), "events": len(events), "inserted": inserted, "updated": updated, "corrected": corrected}


def process_meter(conn: psycopg.Connection, meter_id: str) -> list[dict]:
    """Bring one meter's plays up to date. `conn` must be autocommit; everything happens in one transaction."""
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"playlogger:{meter_id}",))
        meter = conn.execute("SELECT meter_id, venue_id, source FROM meters WHERE meter_id = %s", (meter_id,)).fetchone()
        if meter is None:
            raise ValueError(f"unknown meter {meter_id}")
        conn.execute("INSERT INTO playlogger_state (meter_id) VALUES (%s) ON CONFLICT DO NOTHING", (meter_id,))
        st = conn.execute("SELECT * FROM playlogger_state WHERE meter_id = %s FOR UPDATE", (meter_id,)).fetchone()
        new = conn.execute("SELECT id, window_start FROM match_events WHERE meter_id = %s AND id > %s ORDER BY id",
                           (meter_id, st["last_event_id"])).fetchall()
        if not new:
            return []
        late = st["last_window_start"] is not None and min(r["window_start"] for r in new) < st["last_window_start"]
        results = [rebuild_day(conn, meter, d) for d in sorted({venue_day(r["window_start"]) for r in new})]
        newest = max(r["window_start"] for r in new)
        conn.execute("""UPDATE playlogger_state SET last_event_id = %s, updated_at = now(),
                        last_window_start = GREATEST(COALESCE(last_window_start, %s), %s) WHERE meter_id = %s""",
                     (max(r["id"] for r in new), newest, newest, meter_id))
    if late:
        log.info("%s: late verdicts slotted in by event time: %s", meter_id, results)
    return results


def handle(conn: psycopg.Connection, job: dict) -> None:
    process_meter(conn, job["ref"])


if __name__ == "__main__":
    from server.workers.base import run_jobs
    run_jobs("playlogger", "play", handle)
