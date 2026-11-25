"""Device ingest logic (contract §4): batches, bulk, heartbeat. Pure functions over a DB connection, no web code.

Order of checks for a batch (each failure leaves NOTHING stored):
  1. form valid (core.schema.Batch, sig present)          else 422 {"error":"invalid","detail":…}
  2. meter known (meters table)                           else 404 {"error":"unknown_meter"}
  3. seal valid (Ed25519 over the dict as received)        else 401 {"error":"bad_signature"}
  4. (meter_id, seq) new → store ; same sig → duplicate ; different → 409 {"error":"seq_conflict"}
Stored = raw_batches row (immutable) + windows row + job "match" + live-feed events "batch" and "meter".
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import psycopg
from pydantic import ValidationError

from fairplay_core.schema import Batch, Heartbeat, format_utc, parse_utc
from fairplay_core.signing import verify_dict
from server import calibration, config
from server.db import jobs, notify
from server.registry import get_meter

log = logging.getLogger(__name__)
BULK_MAX = 50


@dataclass
class Result:
    code: int
    body: dict[str, Any]


def _invalid(detail: str) -> Result:
    return Result(422, {"error": "invalid", "detail": detail[:500]})


def _validation_detail(e: ValidationError) -> str:
    return "; ".join(f"{'.'.join(map(str, x['loc'])) or 'body'}: {x['msg']}" for x in e.errors())


def ingest_batch(conn: psycopg.Connection, raw: Any) -> Result:
    """Check and store one batch. Commits on success; the caller owns the connection."""
    if not isinstance(raw, dict):
        return _invalid("body must be a JSON object")
    try:
        batch = Batch.model_validate(raw)
    except ValidationError as e:
        return _invalid(_validation_detail(e))
    if batch.sig is None:
        return _invalid("sig: missing")

    with conn.transaction():
        meter = get_meter(conn, batch.meter_id)
        if meter is None:
            return Result(404, {"error": "unknown_meter"})
        if meter.get("retired_at") is not None:       # D-029: retired by SONACAM
            return Result(403, {"error": "meter_retired"})
        if not verify_dict(meter["public_key_b64"], raw):
            log.warning("bad signature from %s seq %s", batch.meter_id, batch.seq)
            return Result(401, {"error": "bad_signature"})

        latest = conn.execute("SELECT max(window_start) AS m FROM raw_batches WHERE meter_id = %s",
                              (batch.meter_id,)).fetchone()["m"]
        late = latest is not None and batch.window_start_dt < latest
        row = conn.execute(
            """INSERT INTO raw_batches (meter_id, venue_id, seq, window_start, body, late)
               VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (meter_id, seq) DO NOTHING RETURNING id""",
            (batch.meter_id, batch.venue_id, batch.seq, batch.window_start_dt,
             json.dumps(raw, ensure_ascii=False), late)).fetchone()

        if row is None:  # this (meter, seq) was already stored: retry of the same batch, or a conflict
            prev = conn.execute("SELECT body->>'sig' AS sig FROM raw_batches WHERE meter_id = %s AND seq = %s",
                                (batch.meter_id, batch.seq)).fetchone()
            if prev and prev["sig"] == batch.sig:
                return Result(200, {"ack": batch.seq, "status": "duplicate"})
            log.warning("seq conflict %s seq %s", batch.meter_id, batch.seq)
            return Result(409, {"error": "seq_conflict"})

        calibration.check_cell(conn, meter, batch.cell_id)
        ahead = (batch.window_start_dt + timedelta(seconds=10) - datetime.now(timezone.utc)).total_seconds()
        if ahead > config.CLOCK_SKEW_MAX_S:             # a window that ends in the future: meter clock ahead
            calibration.check_clock(conn, meter, -ahead, f"batch seq {batch.seq} ends in the future")
        if batch.venue_id != meter["venue_id"]:
            log.warning("%s sent venue %s but is registered at %s", batch.meter_id, batch.venue_id, meter["venue_id"])
        conn.execute("""INSERT INTO windows (meter_id, window_start, loudness_db, received, source)
                        VALUES (%s, %s, %s, true, %s) ON CONFLICT DO NOTHING""",
                     (batch.meter_id, batch.window_start_dt, batch.loudness_db, meter["source"]))
        m = conn.execute(
            """UPDATE meters SET last_seq = GREATEST(last_seq, %s), last_seen = now(), cell_id = COALESCE(cell_id, %s)
               WHERE meter_id = %s RETURNING last_seen, queued""",
            (batch.seq, batch.cell_id, batch.meter_id)).fetchone()
        jobs.enqueue(conn, "match", str(row["id"]))
        notify(conn, "batch", {"meter_id": batch.meter_id, "venue_id": batch.venue_id, "seq": batch.seq,
                               "window_start": batch.window_start, "late": late})
        notify(conn, "meter", {"meter_id": batch.meter_id, "online": True, "queued": m["queued"],
                               "last_seen": format_utc(m["last_seen"])})
    return Result(200, {"ack": batch.seq, "status": "stored"})


def ingest_bulk(conn: psycopg.Connection, body: Any) -> Result:
    """{"batches": [...≤50]} → each batch handled on its own (one bad batch never blocks the others)."""
    if not isinstance(body, dict) or not isinstance(body.get("batches"), list):
        return _invalid('body must be {"batches": [...]}')
    if len(body["batches"]) > BULK_MAX:
        return _invalid(f"at most {BULK_MAX} batches per bulk request")
    results = []
    for raw in body["batches"]:
        r = ingest_batch(conn, raw)
        seq = raw.get("seq") if isinstance(raw, dict) else None
        if r.code == 200:
            results.append({"seq": seq, "status": r.body["status"]})
        else:
            results.append({"seq": seq, "status": "error", "error": r.body["error"]})
    return Result(200, {"results": results})


def ingest_heartbeat(conn: psycopg.Connection, raw: Any) -> Result:
    if not isinstance(raw, dict):
        return _invalid("body must be a JSON object")
    try:
        hb = Heartbeat.model_validate(raw)
    except ValidationError as e:
        return _invalid(_validation_detail(e))
    if hb.sig is None:
        return _invalid("sig: missing")
    now = datetime.now(timezone.utc)
    with conn.transaction():
        meter = get_meter(conn, hb.meter_id)
        if meter is None:
            return Result(404, {"error": "unknown_meter"})
        if meter.get("retired_at") is not None:       # D-029: retired by SONACAM
            return Result(403, {"error": "meter_retired"})
        if not verify_dict(meter["public_key_b64"], raw):
            return Result(401, {"error": "bad_signature"})
        skew = (now - parse_utc(hb.sent_at)).total_seconds()
        conn.execute("UPDATE meters SET last_seen = %s, queued = %s, clock_skew_s = %s WHERE meter_id = %s",
                     (now, hb.queued, skew, hb.meter_id))
        if calibration.check_clock(conn, meter, skew, "heartbeat") is None:
            calibration.check_window_lag(conn, meter, hb.queued, now)
        notify(conn, "meter", {"meter_id": hb.meter_id, "online": True, "queued": hb.queued,
                               "last_seen": format_utc(now)})
    return Result(200, {"ok": True, "server_time": format_utc(now)})
