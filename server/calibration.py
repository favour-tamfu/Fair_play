"""Meter health (B-T14): calibration → catch rate; clock-skew and moved-meter flags.

Calibration (contract §4 POST /v1/calibration): known songs are played near a meter; the body lists them
{"song_id","played_at"}. An expected play is CAUGHT if the meter produced, for that song, an accepted match whose
back-computed song start (window_start − offset_s) — or a play whose started_at — lies within ±CALIB_TOL_S of
played_at. catch_rate = caught / expected. It becomes meters.catch_rate (used by the share estimate, D-011) when at
least one play was caught. Matching runs a few seconds behind the meter, so runs received in the last
CALIB_RECHECK_S are re-evaluated by the scheduler; re-posting the same run_id also re-evaluates it.

Flags (contract §6 types, flag-only, stats_run_id NULL, SSE "flag"):
  clock_skew   |meter clock − server clock| > CLOCK_SKEW_MAX_S (heartbeat sent_at, or a batch window ending in the
               future); at most one per meter per CLOCK_SKEW_EVERY_S
  meter_moved  a batch reports a cell_id different from the meter's registered one; once per (meter, new cell)
"""
from __future__ import annotations

import json
import logging
from datetime import timedelta
from typing import Any, Optional

import psycopg
from pydantic import ValidationError

from fairplay_core.schema import Calibration, format_utc, parse_utc
from fairplay_core.signing import verify_dict
from server import config
from server.db import notify
from server.registry import get_meter

log = logging.getLogger("calibration")


# ------------------------------------------------------------------ flags

def add_flag(conn, type_: str, meter: dict, detail: str) -> dict:
    f = conn.execute("""INSERT INTO flags (type, venue_id, meter_id, detail) VALUES (%s, %s, %s, %s)
                        RETURNING flag_id, type, song_id, venue_id, detail, created_at""",
                     (type_, meter["venue_id"], meter["meter_id"], detail)).fetchone()
    notify(conn, "flag", {**f, "meter_id": meter["meter_id"], "created_at": format_utc(f["created_at"])})
    log.warning("FLAG %s %s: %s", type_, meter["meter_id"], detail)
    return f


def check_clock(conn, meter: dict, skew_s: float, source: str) -> Optional[dict]:
    """skew_s = server time − meter time (positive: meter clock behind)."""
    if abs(skew_s) <= config.CLOCK_SKEW_MAX_S:
        return None
    recent = conn.execute("""SELECT 1 FROM flags WHERE type = 'clock_skew' AND meter_id = %s
                             AND created_at > now() - make_interval(secs => %s)""",
                          (meter["meter_id"], config.CLOCK_SKEW_EVERY_S)).fetchone()
    if recent:
        return None
    way = "behind" if skew_s > 0 else "ahead of"
    return add_flag(conn, "clock_skew", meter,
                    f"meter clock {abs(skew_s):.1f} s {way} the server ({source}); allowed ±{config.CLOCK_SKEW_MAX_S:g} s")


def check_cell(conn, meter: dict, cell_id: Optional[str]) -> Optional[dict]:
    registered = meter.get("cell_id")
    if not cell_id or not registered or cell_id == registered:
        return None
    detail = f"cell {registered} -> {cell_id} (registered at {meter['venue_id']})"
    seen = conn.execute("SELECT 1 FROM flags WHERE type = 'meter_moved' AND meter_id = %s AND detail = %s",
                        (meter["meter_id"], detail)).fetchone()
    return None if seen else add_flag(conn, "meter_moved", meter, detail)


# ------------------------------------------------------------------ calibration

def evaluate(conn, run_id: str) -> Optional[dict]:
    """(Re)compute one calibration run; updates calibrations and, if anything was caught, meters.catch_rate."""
    run = conn.execute("SELECT * FROM calibrations WHERE run_id = %s", (run_id,)).fetchone()
    if run is None:
        return None
    tol = timedelta(seconds=config.CALIB_TOL_S)
    expected = run["expected"]
    caught = []
    for e in expected:
        t = parse_utc(e["played_at"])
        hit = conn.execute(
            """SELECT 1 FROM match_events WHERE meter_id = %s AND song_id = %s AND accepted
                 AND window_start - make_interval(secs => COALESCE(offset_s, 0)) BETWEEN %s AND %s
               UNION ALL
               SELECT 1 FROM plays WHERE meter_id = %s AND song_id = %s AND chain = 'live'
                 AND started_at BETWEEN %s AND %s
               LIMIT 1""",
            (run["meter_id"], e["song_id"], t - tol, t + tol, run["meter_id"], e["song_id"], t - tol, t + tol)).fetchone()
        caught.append(bool(hit))
    matched, total = sum(caught), len(expected)
    rate = matched / total if total else 0.0
    applied = matched > 0
    pending = conn.execute("""SELECT count(*) AS n FROM raw_batches WHERE meter_id = %s AND NOT processed
                              AND window_start BETWEEN %s AND %s""",
                           (run["meter_id"], run["started_at"] - tol, run["ended_at"] + tol)).fetchone()["n"]
    conn.execute("""UPDATE calibrations SET matched = %s, total = %s, catch_rate = %s, applied = %s, updated_at = now(),
                    detail = %s WHERE run_id = %s""",
                 (matched, total, rate, applied, json.dumps([{**e, "caught": c} for e, c in zip(expected, caught)]), run_id))
    if applied:
        conn.execute("UPDATE meters SET catch_rate = %s WHERE meter_id = %s", (rate, run["meter_id"]))
    return {"run_id": run_id, "meter_id": run["meter_id"], "matched": matched, "total": total,
            "catch_rate": round(rate, 4), "applied": applied, "pending_windows": pending}


def ingest_calibration(conn: psycopg.Connection, raw: Any):
    from server.ingest import Result, _invalid, _validation_detail
    if not isinstance(raw, dict):
        return _invalid("body must be a JSON object")
    try:
        cal = Calibration.model_validate(raw)
    except ValidationError as e:
        return _invalid(_validation_detail(e))
    if cal.sig is None:
        return _invalid("sig: missing")
    with conn.transaction():
        meter = get_meter(conn, cal.meter_id)
        if meter is None:
            return Result(404, {"error": "unknown_meter"})
        if not verify_dict(meter["public_key_b64"], raw):
            return Result(401, {"error": "bad_signature"})
        expected = [{"song_id": e.song_id, "played_at": e.played_at} for e in cal.expected]
        conn.execute("""INSERT INTO calibrations (run_id, meter_id, started_at, ended_at, expected, matched, total, catch_rate)
                        VALUES (%s, %s, %s, %s, %s, 0, %s, 0)
                        ON CONFLICT (run_id) DO UPDATE SET started_at = EXCLUDED.started_at, ended_at = EXCLUDED.ended_at,
                          expected = EXCLUDED.expected, total = EXCLUDED.total, received_at = now()""",
                     (cal.run_id, cal.meter_id, parse_utc(cal.started_at), parse_utc(cal.ended_at),
                      json.dumps(expected), len(expected)))
        out = evaluate(conn, cal.run_id)
    log.info("calibration %s: %s", cal.run_id, out)
    return Result(200, {"ok": True, **{k: v for k, v in out.items() if k != "meter_id"}})


def recheck_recent(conn) -> list[dict]:
    """Scheduler duty: re-evaluate runs received in the last CALIB_RECHECK_S (matching may still be catching up)."""
    out = []
    for r in conn.execute("SELECT run_id FROM calibrations WHERE received_at > now() - make_interval(secs => %s)",
                          (config.CALIB_RECHECK_S,)).fetchall():
        with conn.transaction():
            out.append(evaluate(conn, r["run_id"]))
    return out

