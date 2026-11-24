"""Matcher worker (B-T05, "the detective"): each received batch → one match verdict.

Job "match", ref = raw_batches.id:
  1. load the stored batch, decode its peaks, make_hashes (frames relative to the window)
  2. match_window against the in-memory DbIndex (synced with songs that are ready)
  3. insert match_events — ALSO when rejected (kept for evaluation; song_id = best candidate)
  4. raw_batches.processed = true; queue a "play" job for the meter (once: skipped if one is already queued)
  5. NOTIFY "match" for the live feed (song only shown when accepted)
Idempotent: a retried job finds the existing verdict and does nothing new.
"""
from __future__ import annotations

import logging
import time

import psycopg

from fairplay_core.landmarks import make_hashes, match_window
from fairplay_core.schema import Batch, format_utc
from server.db import jobs, notify
from server.fp.index import DbIndex

log = logging.getLogger("matcher")
INDEX = DbIndex()


def process(conn: psycopg.Connection, raw_batch_id: int, index: DbIndex = INDEX) -> dict:
    """Match one stored batch. Returns the match_events row (new or existing). `conn` must be autocommit."""
    existing = conn.execute("SELECT * FROM match_events WHERE raw_batch_id = %s", (raw_batch_id,)).fetchone()
    if existing:
        return existing
    rb = conn.execute("SELECT id, meter_id, venue_id, window_start, body FROM raw_batches WHERE id = %s",
                      (raw_batch_id,)).fetchone()
    if rb is None:
        raise ValueError(f"raw batch {raw_batch_id} not found")

    t0 = time.perf_counter()
    index.sync(conn)
    batch = Batch.model_validate(rb["body"])          # stored bodies were validated at ingest
    r = match_window(make_hashes(batch.peak_records()), index)
    ms = (time.perf_counter() - t0) * 1000

    with conn.transaction():
        row = conn.execute(
            """INSERT INTO match_events (raw_batch_id, meter_id, venue_id, window_start, song_id, offset_s,
                                         best_score, second_score, confidence, accepted, loudness_db)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (raw_batch_id) DO NOTHING RETURNING *""",
            (rb["id"], rb["meter_id"], rb["venue_id"], rb["window_start"], r.song_id, round(r.offset_s, 3) + 0.0,
             r.best_score, r.second_score, round(r.confidence, 4), r.accepted, batch.loudness_db)).fetchone()
        if row is None:                                # another worker got there first
            return conn.execute("SELECT * FROM match_events WHERE raw_batch_id = %s", (raw_batch_id,)).fetchone()
        conn.execute("UPDATE raw_batches SET processed = true WHERE id = %s", (rb["id"],))
        if not conn.execute("SELECT 1 FROM jobs WHERE kind = 'play' AND ref = %s AND status = 'queued' LIMIT 1",
                            (rb["meter_id"],)).fetchone():
            jobs.enqueue(conn, "play", rb["meter_id"])
        title = None
        if r.accepted:
            t = conn.execute("SELECT title FROM songs WHERE song_id = %s", (r.song_id,)).fetchone()
            title = t["title"] if t else None
        notify(conn, "match", {"meter_id": rb["meter_id"], "venue_id": rb["venue_id"],
                               "song_id": r.song_id if r.accepted else None, "title": title,
                               "offset_s": round(r.offset_s, 1) + 0.0, "confidence": round(r.confidence, 3),
                               "accepted": r.accepted, "window_start": format_utc(rb["window_start"])})
    log.info("batch %s %s seq %s: %s score %d/%d (%d hashes) in %.0f ms", rb["id"], rb["meter_id"], batch.seq,
             f"MATCH {r.song_id} @ {r.offset_s:.1f}s" if r.accepted else "no match",
             r.best_score, r.second_score, r.n_hashes, ms)
    return row


def handle(conn: psycopg.Connection, job: dict) -> None:
    process(conn, int(job["ref"]))


if __name__ == "__main__":
    from server.workers.base import run_jobs
    run_jobs("matcher", "match", handle)
