"""One stats run: plays of a period -> weights -> national shares with ranges -> stored + NOTIFY "stats" (B-T10).

    run_stats(conn, period="live", mode="standardised") -> {"stats_run_id", "status": "done", "duration_ms", ...}

mode = standardised : fair-play rules sr-1.0 (streak/cooldown; loop/audience/concentration flags, D-009)
mode = raw          : every play counts 1, no rules, no flags (the "Raw" side of the dashboard toggle)

Writes stats_runs, play_weights, shares and (standardised only) flags, in ONE transaction, serialised by advisory
lock 43 so two runs never interleave. The previous stats flags of the same period are replaced; runs older than the
last config.STATS_KEEP_RUNS per (period, mode) are pruned with their weights and shares.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd
import psycopg

from server import config
from server.db import notify
from server.stats import estimate
from server.stats.fairplay import compute_weights
from server.stats.periods import ACTIVE, PERIODS, period_bounds, period_sql

log = logging.getLogger("stats")
MODES = ("standardised", "raw")
LOCK = 43


def load_plays(conn, period: str) -> pd.DataFrame:
    where, args = period_sql(period)
    rows = conn.execute(f"""SELECT p.play_id, p.meter_id, p.venue_id, p.song_id, p.started_at,
                                   COALESCE(x.duration_s, p.duration_s) AS duration_s,
                                   COALESCE(x.loudness_db, p.loudness_db) AS loudness_db
                            FROM plays p LEFT JOIN play_extents x USING (play_id)
                            WHERE {ACTIVE} AND {where}""", args).fetchall()
    cols = ["play_id", "meter_id", "venue_id", "song_id", "started_at", "duration_s", "loudness_db"]
    return pd.DataFrame(rows, columns=cols)


def load_meters(conn, meter_ids: list[str], period: str = "live") -> pd.DataFrame:
    """Catch rate per meter (D-011: no opening hours, no listening fraction). Mock month: the mock meters (D-013)."""
    table = "mock_meters" if period == "mock_month" else "meters"
    rows = conn.execute(f"SELECT meter_id, catch_rate FROM {table} WHERE meter_id = ANY(%s)", (meter_ids,)).fetchall()
    return pd.DataFrame(rows, columns=["meter_id", "catch_rate"])


def load_loudness_thresholds(conn, venue_ids: list[str], start: datetime, end: datetime,
                             period: str = "live") -> pd.DataFrame:
    """Venue loudness percentile for the audience flag (live windows).

    Mock month: none (D-013). A's windows_observed slots are on another loudness scale than plays_observed
    (slots about -22 dB at every hour, plays about -28 dB), so a slot percentile would mark ~38 % of plays quiet.
    The audience flag then uses its other test only: plays outside the venue's active hours.
    """
    if period == "mock_month":
        return pd.DataFrame(columns=["venue_id", "n_windows", "threshold_db"])
    rows = conn.execute("""SELECT m.venue_id, count(*) AS n_windows,
                                  percentile_cont(%s) WITHIN GROUP (ORDER BY w.loudness_db) AS threshold_db
                           FROM windows w JOIN meters m USING (meter_id)
                           WHERE w.received AND w.loudness_db IS NOT NULL AND m.venue_id = ANY(%s)
                             AND w.window_start >= %s AND w.window_start < %s
                           GROUP BY m.venue_id""", (config.AUDIENCE_PCTL / 100, venue_ids, start, end)).fetchall()
    return pd.DataFrame(rows, columns=["venue_id", "n_windows", "threshold_db"])


def new_run_id(conn, now: datetime) -> str:
    """R-yyyymmddHHMMSS, strictly increasing: never reuses the id of a pruned run (the newest run is never pruned)."""
    t = now.replace(microsecond=0)
    last = conn.execute("SELECT max(stats_run_id) AS m FROM stats_runs").fetchone()["m"]
    if last:
        t = max(t, datetime.strptime(last[2:], "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc) + timedelta(seconds=1))
    return "R-" + t.strftime("%Y%m%d%H%M%S")


def plays_fingerprint(conn, period: str) -> tuple:
    """Cheap 'did anything change?' key for the scheduler (plays, corrections, growing extents)."""
    where, args = period_sql(period)
    r = conn.execute(f"""SELECT count(*) AS n, max(p.seq_no) AS last,
                                (SELECT count(*) FROM play_corrections) AS corr,
                                (SELECT max(updated_at) FROM play_extents) AS ext
                         FROM plays p WHERE {ACTIVE} AND {where}""", args).fetchone()
    return (r["n"], r["last"], r["corr"], r["ext"])


def run_stats(conn: psycopg.Connection, period: str = "live", mode: str = "standardised",
              pot_fcfa: int = config.POT_DEFAULT_FCFA) -> dict[str, Any]:
    if period not in PERIODS or mode not in MODES:
        raise ValueError(f"bad period/mode {period!r}/{mode!r}")
    t0 = time.monotonic()
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK,))
        now = datetime.now(timezone.utc)
        start, end = period_bounds(conn, period)
        plays = load_plays(conn, period)
        meter_ids = sorted(set(plays["meter_id"])) if not plays.empty else []
        venue_ids = sorted(set(plays["venue_id"])) if not plays.empty else []

        if mode == "standardised":
            songs = pd.DataFrame(conn.execute("SELECT song_id, duration_s FROM songs").fetchall(),
                                 columns=["song_id", "duration_s"])
            fp = compute_weights(plays, songs, loudness_thresholds=load_loudness_thresholds(conn, venue_ids, start, end, period))
            weights, flags, rule = fp.weights, fp.flags, config.RULE_VERSION
        else:
            weights = pd.DataFrame({"play_id": plays["play_id"], "weight": 1.0, "reasons": [[] for _ in range(len(plays))]})
            flags, rule = [], "raw"

        pw = plays[["play_id", "meter_id", "song_id"]].merge(weights, on="play_id") if not plays.empty else \
            pd.DataFrame(columns=["play_id", "meter_id", "song_id", "weight"])
        est = estimate.estimate_shares(pw, load_meters(conn, meter_ids, period))

        rid = new_run_id(conn, now)
        params = {"pot_fcfa": pot_fcfa, "escrow_share": 0.0, "n_plays": int(len(plays)),       # D-011: no escrow
                  "n_meters": len(meter_ids), "n_venues": len(venue_ids), "period_start": start.isoformat(),
                  "period_end": end.isoformat(),
                  "modifiers_adjust_weights": config.MODIFIERS_ADJUST_WEIGHTS if mode == "standardised" else None}
        conn.execute("""INSERT INTO stats_runs (stats_run_id, period, mode, rule_version, started_at, params)
                        VALUES (%s, %s, %s, %s, %s, %s)""", (rid, period, mode, rule, now, json.dumps(params)))
        with conn.cursor().copy("COPY play_weights (play_id, rule_version, stats_run_id, weight, reasons) FROM STDIN") as cp:
            for r in weights.itertuples(index=False):
                cp.write_row((r.play_id, rule, rid, float(r.weight), list(r.reasons)))

        song_flags: dict[str, set] = {}
        for f in flags:
            if f["song_id"]:
                song_flags.setdefault(f["song_id"], set()).add(f["type"])
        with conn.cursor().copy("COPY shares (stats_run_id, song_id, raw_plays, weighted_plays, share, ci_low, ci_high, "
                                "flags) FROM STDIN") as cp:
            for r in est.shares.itertuples(index=False):
                cp.write_row((rid, r.song_id, int(r.raw_plays), float(r.weighted_plays), float(r.share),
                              float(r.ci_low), float(r.ci_high), sorted(song_flags.get(r.song_id, ()))))

        if mode == "standardised":                       # replace this period's previous stats flags
            conn.execute("""DELETE FROM flags WHERE stats_run_id IN
                            (SELECT stats_run_id FROM stats_runs WHERE period = %s AND stats_run_id <> %s)""", (period, rid))
            with conn.cursor().copy("COPY flags (type, song_id, venue_id, meter_id, detail, stats_run_id) FROM STDIN") as cp:
                for f in flags:
                    cp.write_row((f["type"], f["song_id"], f["venue_id"], f["meter_id"], f["detail"], rid))

        old = [r["stats_run_id"] for r in conn.execute(
            """SELECT stats_run_id FROM stats_runs WHERE period = %s AND mode = %s AND stats_run_id <> %s
               ORDER BY started_at DESC OFFSET %s""", (period, mode, rid, config.STATS_KEEP_RUNS - 1))]
        if old:
            for table in ("play_weights", "shares", "flags", "stats_runs"):
                conn.execute(f"DELETE FROM {table} WHERE stats_run_id = ANY(%s)", (old,))

        ms = int((time.monotonic() - t0) * 1000)
        params["duration_ms"] = ms
        conn.execute("UPDATE stats_runs SET finished_at = now(), params = %s WHERE stats_run_id = %s",
                     (json.dumps(params), rid))
        notify(conn, "stats", {"stats_run_id": rid, "period": period, "mode": mode})
    log.info("stats %s %s/%s: %d plays, %d songs, %d flags, %d ms", rid, period, mode, len(plays),
             len(est.shares), len(flags), ms)
    return {"stats_run_id": rid, "status": "done", "duration_ms": ms, "period": period, "mode": mode,
            "n_plays": int(len(plays)), "n_songs": int(len(est.shares)), "n_flags": len(flags)}


def run_both(conn: psycopg.Connection, period: str = "live") -> dict[str, Any]:
    """Raw then standardised (the dashboard toggle needs both). Returns the standardised run's answer."""
    raw = run_stats(conn, period, "raw")
    std = run_stats(conn, period, "standardised")
    return {**std, "duration_ms": raw["duration_ms"] + std["duration_ms"], "raw_stats_run_id": raw["stats_run_id"]}
