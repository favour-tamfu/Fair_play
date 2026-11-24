"""B-T06: play logger worker on the database — live growth, immutability, late batches, restarts, ledger, feed."""
import json
import logging
from datetime import datetime, timedelta, timezone

import psycopg
import pytest

from server.db import EVENTS_CHANNEL, connect, jobs
from server.ledger import chain
from server.registry import upsert_meter
from server.tools.make_test_vectors import OUT as TV_DIR
from server.workers import playlogger
from server.workers.base import run_one

T0 = datetime(2026, 11, 24, 20, 0, tzinfo=timezone.utc)   # 21:00 local
M = "M-90"


@pytest.fixture(autouse=True)
def clean(migrated_db):
    with connect(migrated_db, autocommit=True) as c:
        c.execute("TRUNCATE raw_batches, match_events, plays, play_extents, play_corrections, playlogger_state, "
                  "unidentified, jobs, songs, owners, fp_hashes, flags RESTART IDENTITY CASCADE")
        with c.transaction():
            upsert_meter(c, json.loads((TV_DIR / "tv_keys.json").read_text(encoding="utf-8")))
        for sid, title, dur in (("S-000001", "Makossa Night", 240.0), ("S-000002", "Bikutsi Morning", 200.0)):
            c.execute("INSERT INTO songs (song_id, title, artist_name, status, duration_s) VALUES (%s,%s,'T','ready',%s)",
                      (sid, title, dur))


def add(db, windows, song="S-000001", loud=-20.0):
    """Insert match verdicts: windows = [(seconds after T0, song offset or None)]."""
    with connect(db, autocommit=True) as c:
        for t, off in windows:
            c.execute("""INSERT INTO match_events (meter_id, venue_id, window_start, song_id, offset_s, best_score,
                         second_score, confidence, accepted, loudness_db) VALUES (%s,'V-BUEA-CIMFEST',%s,%s,%s,50,1,0.3,%s,%s)""",
                      (M, T0 + timedelta(seconds=t), song if off is not None else None, off or 0, off is not None, loud))


def run(db):
    with connect(db, autocommit=True) as c:
        return playlogger.process_meter(c, M)


def q(db, sql, *a):
    with connect(db) as c:
        return c.execute(sql, a).fetchall()


def plays(db):
    return q(db, """SELECT p.play_id, p.song_id, p.started_at, p.n_windows AS n0, p.duration_s AS d0, p.chain_hash,
                    p.prev_chain_hash, p.source, x.n_windows, x.ended_at FROM plays p JOIN play_extents x USING (play_id)
                    ORDER BY p.seq_no""")


def test_live_play_appears_on_third_window_and_then_grows(migrated_db):
    for k in range(2):                                  # 240 s song: 2 windows cover 20 s < 30 s → not yet
        add(migrated_db, [(10 * k, 20 + 10 * k)])
        run(migrated_db)
    assert plays(migrated_db) == []
    add(migrated_db, [(20, 40)])
    run(migrated_db)                                    # third window → confirmed
    p0 = plays(migrated_db)
    assert len(p0) == 1 and p0[0]["started_at"] == T0 - timedelta(seconds=20) and p0[0]["source"] == "virtual"
    for k in range(3, 8):
        add(migrated_db, [(10 * k, 20 + 10 * k)])
        run(migrated_db)
    p1 = plays(migrated_db)
    assert len(p1) == 1 and p1[0]["n_windows"] == 8 and p1[0]["ended_at"] == T0 + timedelta(seconds=80)
    # the chained row itself never changes as the play grows
    assert (p1[0]["n0"], p1[0]["d0"], p1[0]["chain_hash"]) == (p0[0]["n0"], p0[0]["d0"], p0[0]["chain_hash"])


def test_two_songs_two_plays_chained(migrated_db):
    add(migrated_db, [(0, 0), (10, 10), (20, 20)])
    add(migrated_db, [(30, 0), (40, 10), (50, 20)], song="S-000002")
    run(migrated_db)
    p = plays(migrated_db)
    assert [r["song_id"] for r in p] == ["S-000001", "S-000002"]
    assert p[0]["prev_chain_hash"] == chain.GENESIS and p[1]["prev_chain_hash"] == p[0]["chain_hash"]
    full = q(migrated_db, "SELECT * FROM plays ORDER BY seq_no")
    assert chain.link(chain.GENESIS, full[0]) == full[0]["chain_hash"]          # stored hash = recomputed hash
    assert chain.link(full[0]["chain_hash"], full[1]) == full[1]["chain_hash"]


def test_late_windows_slot_in_by_event_time_without_duplicates(migrated_db):
    """Network cut: windows 3–6 arrive first, the earlier windows 0–2 arrive later (out of order)."""
    add(migrated_db, [(30, 30), (40, 40), (50, 50), (60, 60)])
    run(migrated_db)
    assert len(plays(migrated_db)) == 1
    add(migrated_db, [(0, 0), (10, 10), (20, 20)])          # late: earlier event time, newer ids
    res = run(migrated_db)
    p = plays(migrated_db)
    assert len(p) == 1 and p[0]["n_windows"] == 7 and p[0]["started_at"] == T0     # same play, extended back
    assert q(migrated_db, "SELECT count(*) AS n FROM play_corrections")[0]["n"] == 0
    assert res[0]["updated"] == 1 and res[0]["inserted"] == 0


def test_late_earlier_song_is_inserted_in_the_right_place(migrated_db):
    add(migrated_db, [(100, 0), (110, 10), (120, 20)])
    run(migrated_db)
    add(migrated_db, [(0, 0), (10, 10), (20, 20)], song="S-000002")      # an earlier song, arriving late
    run(migrated_db)
    by_time = q(migrated_db, "SELECT song_id FROM plays ORDER BY started_at")
    assert [r["song_id"] for r in by_time] == ["S-000002", "S-000001"]


def test_late_windows_that_change_the_story_write_corrections_not_edits(migrated_db):
    """A logged play turns out to be two different songs once late windows arrive → original kept + correction."""
    add(migrated_db, [(0, 0), (10, 10), (20, 20), (60, 60), (70, 70), (80, 80)])
    run(migrated_db)
    before = plays(migrated_db)
    assert len(before) == 1
    add(migrated_db, [(30, 0), (40, 10), (50, 20)], song="S-000002")     # a different song was playing in between
    run(migrated_db)
    after = plays(migrated_db)
    assert [r["song_id"] for r in after] == ["S-000001", "S-000002", "S-000001"]
    assert after[0]["chain_hash"] == before[0]["chain_hash"]           # original row untouched
    assert after[0]["n_windows"] == 3                                    # its extent now ends before the other song


def test_restart_and_rerun_are_idempotent(migrated_db):
    add(migrated_db, [(0, 0), (10, 10), (20, 20), (30, 30)])
    run(migrated_db)
    before = plays(migrated_db)
    with connect(migrated_db, autocommit=True) as c:
        c.execute("DELETE FROM playlogger_state")                         # crash: state lost
        jobs.enqueue(c, "play", M)
        assert run_one(c, "play", playlogger.handle, logging.getLogger("t"))
    assert plays(migrated_db) == before
    assert run(migrated_db) == []                                         # nothing new → nothing done
    assert q(migrated_db, "SELECT count(*) AS n FROM play_corrections")[0]["n"] == 0


def test_play_event_on_feed(migrated_db):
    add(migrated_db, [(0, 0), (10, 10), (20, 20)])
    with psycopg.connect(migrated_db, autocommit=True) as listener:
        listener.execute(f"LISTEN {EVENTS_CHANNEL}")
        run(migrated_db)
        got = [json.loads(n.payload) for n in listener.notifies(timeout=2, stop_after=1)]
    assert got[0]["event"] == "play"
    d = got[0]["data"]
    assert d["song_id"] == "S-000001" and d["title"] == "Makossa Night" and d["source"] == "virtual"
    assert d["started_at"] == "2026-11-24T20:00:00.000Z" and d["play_id"].startswith("P-")


def test_unidentified_music_seconds(migrated_db):
    add(migrated_db, [(0, 0), (10, 10), (20, 20)])
    add(migrated_db, [(100, None), (110, None), (120, None)])              # loud, no match
    add(migrated_db, [(200, None)], loud=-60.0)                            # silent bar
    run(migrated_db)
    assert q(migrated_db, "SELECT seconds FROM unidentified")[0]["seconds"] == 30.0


def test_night_boundary(migrated_db):
    """01:30 local belongs to the previous evening's venue-night (18:00–02:00 is one night)."""
    late_night = datetime(2026, 11, 25, 0, 30, tzinfo=timezone.utc)       # 01:30 local, 25 Nov
    assert str(playlogger.venue_day(late_night)) == "2026-11-24"
    assert str(playlogger.venue_day(datetime(2026, 11, 25, 6, 0, tzinfo=timezone.utc))) == "2026-11-25"
