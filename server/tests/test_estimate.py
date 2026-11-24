"""B-T10: estimation (brief §7.3 + D-011), stats runs in the DB, POST /api/v1/stats/run, scheduler stats duty."""
import json
from datetime import datetime, timedelta, timezone

import pandas as pd
import psycopg
import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from server import config
from server.db import EVENTS_CHANNEL, connect
from server.ledger import chain
from server.stats import estimate
from server.stats.run import run_both, run_stats
from server.workers.scheduler import Scheduler

UTC = timezone.utc


# ---------------------------------------------------------------- pure estimation

def pw(rows):
    return pd.DataFrame([{"meter_id": m, "song_id": s, "weight": w} for m, s, w, k in rows for _ in range(k)])


def test_every_bar_metered_sum_of_counted_plays():
    """D-011: a meter in every bar -> national total = plain sum over meters (no scaling, no opening hours)."""
    meters = pd.DataFrame({"meter_id": ["a", "b", "c"], "catch_rate": [1.0, 1.0, 1.0]})
    plays = pw([("a", "X", 1, 2), ("b", "Y", 1, 2), ("c", "X", 1, 4), ("c", "Y", 0.5, 2)])
    s = estimate.estimate_shares(plays, meters).shares.set_index("song_id")
    assert s.loc["X", "expanded"] == 6 and s.loc["Y", "expanded"] == 3
    assert s.loc["X", "share"] == pytest.approx(2 / 3) and list(s.index) == ["X", "Y"]
    assert s["raw_plays"].to_dict() == {"X": 6, "Y": 4} and s["weighted_plays"].to_dict() == {"X": 6, "Y": 3}
    assert (s["ci_low"] == s["share"]).all() and (s["ci_high"] == s["share"]).all()     # no sampling range
    assert s["share"].sum() == pytest.approx(1.0)


def test_catch_rate_correction_and_defaults():
    meters = pd.DataFrame({"meter_id": ["a", "b"], "catch_rate": [0.5, 1.0]})
    s = estimate.estimate_shares(pw([("a", "X", 1, 1), ("b", "Y", 1, 1)]), meters).shares.set_index("song_id")
    assert s.loc["X", "share"] == pytest.approx(2 / 3)                     # meter a misses half -> 1 heard ≈ 2 played
    assert list(estimate.catch_rates(["a", "z"], meters)) == [0.5, config.DEFAULT_CATCH_RATE]
    plays = pw([("m", "X", 1, 3), ("m", "Y", 0.5, 2)])
    e1, e2 = estimate.estimate_shares(plays), estimate.estimate_shares(plays)
    assert e1.shares.equals(e2.shares) and e1.shares.set_index("song_id").loc["X", "share"] == pytest.approx(0.75)
    assert estimate.estimate_shares(plays.iloc[:0]).shares.empty


# ---------------------------------------------------------------- stats runs in the DB

T0 = datetime(2026, 11, 24, 20, 0, tzinfo=UTC)


def seed(db, rows):
    """rows: (minutes after T0, song) on live meter M-07 at V-BUEA-CIMFEST."""
    with connect(db, autocommit=True) as c, c.transaction():
        c.execute("TRUNCATE plays, play_extents, play_corrections, play_weights, stats_runs, shares, flags, "
                  "windows, songs, meters, venues CASCADE")
        c.execute("INSERT INTO venues (venue_id, name, stratum, bars_in_stratum, source) VALUES "
                  "('V-BUEA-CIMFEST','CIMFEST demo table','BUEA-S',40,'live')")
        c.execute("INSERT INTO meters (meter_id, venue_id, public_key_b64, source, catch_rate) VALUES "
                  "('M-07','V-BUEA-CIMFEST','k','live',0.8)")
        for sid in sorted({s for _, s in rows}):
            c.execute("INSERT INTO songs (song_id, title, artist_name, status, duration_s) VALUES (%s,%s,'T','ready',200)",
                      (sid, sid))
        for i, (m, s) in enumerate(rows):
            p = {"play_id": f"P-st{i:08d}", "meter_id": "M-07", "venue_id": "V-BUEA-CIMFEST", "song_id": s,
                 "started_at": T0 + timedelta(minutes=m), "duration_s": 30.0, "n_windows": 3}
            prev, h = chain.append(c, p)
            c.execute("""INSERT INTO plays (play_id, meter_id, venue_id, song_id, started_at, duration_s, n_windows, source,
                         prev_chain_hash, chain_hash) VALUES (%s,'M-07','V-BUEA-CIMFEST',%s,%s,30,3,'live',%s,%s)""",
                      (p["play_id"], s, p["started_at"], prev, h))
            c.execute("INSERT INTO play_extents (play_id, ended_at, n_windows, duration_s, venue_day) VALUES (%s,%s,20,200,%s)",
                      (p["play_id"], p["started_at"] + timedelta(seconds=200), p["started_at"].date()))
        for k in range(120):
            c.execute("INSERT INTO windows (meter_id, window_start, loudness_db, received, source) VALUES "
                      "('M-07', %s, -20, true, 'live')", (T0 + timedelta(seconds=10 * k),))


# T-SR-1 night: A x7 -> 3.75 counted
A, B, C, D = "S-000001", "S-000002", "S-000003", "S-000004"
TSR1 = [(0, A), (4, A), (8, A), (12, A), (16, B), (20, A), (24, C), (28, D), (60, A), (135, A)]


@pytest.fixture
def db(migrated_db, monkeypatch):
    monkeypatch.setattr(config, "DATABASE_URL", migrated_db)
    seed(migrated_db, TSR1)
    return migrated_db


def test_run_stats_raw_vs_standardised(db):
    with connect(db, autocommit=True) as c:
        both = run_both(c, "live")
        std = c.execute("SELECT * FROM stats_runs WHERE stats_run_id = %s", (both["stats_run_id"],)).fetchone()
        raw = c.execute("SELECT * FROM stats_runs WHERE stats_run_id = %s", (both["raw_stats_run_id"],)).fetchone()
        assert (std["mode"], std["rule_version"], raw["mode"], raw["rule_version"]) == \
            ("standardised", "sr-1.0", "raw", "raw")
        assert std["finished_at"] is not None and std["params"]["n_plays"] == 10
        assert std["params"]["escrow_share"] == 0.0                         # D-011: no escrow
        sh = {r["song_id"]: r for r in c.execute("SELECT * FROM shares WHERE stats_run_id = %s", (std["stats_run_id"],))}
        rs = {r["song_id"]: r for r in c.execute("SELECT * FROM shares WHERE stats_run_id = %s", (raw["stats_run_id"],))}
        assert sh[A]["raw_plays"] == 7 and sh[A]["weighted_plays"] == 3.75 and rs[A]["weighted_plays"] == 7
        assert sh[A]["share"] == pytest.approx(3.75 / 6.75) and rs[A]["share"] == pytest.approx(0.7)
        assert sum(r["share"] for r in sh.values()) == pytest.approx(1)
        assert sh[A]["flags"] == ["cooldown"]
        w = {r["play_id"]: (r["weight"], r["reasons"]) for r in
             c.execute("SELECT * FROM play_weights WHERE stats_run_id = %s", (std["stats_run_id"],))}
        assert w["P-st00000005"] == (0, ["cooldown"]) and len(w) == 10
        assert c.execute("SELECT count(*) AS n FROM play_weights WHERE stats_run_id = %s",
                         (raw["stats_run_id"],)).fetchone()["n"] == 10
        flags = c.execute("SELECT type, song_id, stats_run_id FROM flags").fetchall()
        assert [(f["type"], f["song_id"]) for f in flags] == [("cooldown", A)]


def test_rerun_replaces_flags_and_prunes_old_runs(db):
    with connect(db, autocommit=True) as c:
        ids = [run_stats(c, "live", "standardised")["stats_run_id"] for _ in range(config.STATS_KEEP_RUNS + 2)]
        assert len(set(ids)) == len(ids)                                   # unique ids even within one second
        kept = [r["stats_run_id"] for r in c.execute("SELECT stats_run_id FROM stats_runs ORDER BY started_at")]
        assert kept == ids[-config.STATS_KEEP_RUNS:]
        assert c.execute("SELECT count(DISTINCT stats_run_id) AS n FROM play_weights").fetchone()["n"] == config.STATS_KEEP_RUNS
        assert c.execute("SELECT count(*) AS n FROM flags").fetchone()["n"] == 1      # not one per run


def test_stats_notify_and_api(db):
    from server.api.main import app
    schema = json.loads((config.SCHEMAS_DIR / "shares.schema.json").read_text("utf-8"))
    with psycopg.connect(db, autocommit=True) as listener, TestClient(app) as cl:
        listener.execute(f"LISTEN {EVENTS_CHANNEL}")
        r = cl.post("/api/v1/stats/run", params={"period": "live"}).json()
        assert r["status"] == "done" and r["stats_run_id"].startswith("R-") and isinstance(r["duration_ms"], int)
        got = [json.loads(n.payload) for n in listener.notifies(timeout=2, stop_after=2)]
        assert [(g["event"], g["data"]["mode"]) for g in got] == [("stats", "raw"), ("stats", "standardised")]
        for mode, top in (("standardised", 3.75), ("raw", 7)):
            body = cl.get("/api/v1/shares", params={"period": "live", "mode": mode}).json()
            assert list(Draft202012Validator(schema).iter_errors(body)) == []
            assert body["rows"][0]["song_id"] == A and body["rows"][0]["weighted_plays"] == top
            assert sum(x["amount_fcfa"] for x in body["rows"]) == body["pot_fcfa"]
        assert cl.get("/api/v1/overview", params={"period": "live"}).json()["plays_counted"] == 6.75
        assert [f["type"] for f in cl.get("/api/v1/flags", params={"period": "live"}).json()] == ["cooldown"]
        assert cl.get("/api/v1/flags", params={"period": "mock_month"}).json() == []
        assert cl.post("/api/v1/stats/run", params={"period": "yesterday"}).status_code == 422


def test_scheduler_runs_stats_only_when_plays_change(db):
    sch = Scheduler()
    with connect(db, autocommit=True) as c:
        assert sch.check_stats(c) == ["live"]
        assert sch.check_stats(c) == []                                   # nothing changed
        c.execute("INSERT INTO play_corrections (play_id, reason, detail) VALUES "
                  "('P-st00000009','not_confirmed_on_recompute','{}')")
        assert sch.check_stats(c) == ["live"]
        assert c.execute("SELECT count(*) AS n FROM stats_runs").fetchone()["n"] == 4
        top = c.execute("""SELECT sh.weighted_plays FROM shares sh JOIN stats_runs r USING (stats_run_id)
                           WHERE r.mode = 'standardised' AND sh.song_id = %s ORDER BY r.started_at DESC LIMIT 1""", (A,)).fetchone()
        assert top["weighted_plays"] == 2.75                              # superseded play no longer counted


def test_empty_period_runs_cleanly(migrated_db):
    with connect(migrated_db, autocommit=True) as c:
        r = run_stats(c, "mock_month", "standardised")
        assert r["n_plays"] == 0 and r["n_songs"] == 0
        assert c.execute("SELECT count(*) AS n FROM shares WHERE stats_run_id = %s", (r["stats_run_id"],)).fetchone()["n"] == 0
