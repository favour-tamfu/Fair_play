"""Activity log for SONACAM admins (D-024).

Every live event the server already publishes (db.notify) is also written here as one readable line, plus what the
live feed does not carry: meters going online/offline, rejected device requests, admin actions (done or refused) and
songs becoming ready. Admins read it on the admin page (filters, live, CSV) through /api/v1/admin/activity.
Writing never breaks the action it describes: a failed insert is logged and ignored.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import psycopg
from psycopg.types.json import Jsonb

log = logging.getLogger("fairplay.activity")

KINDS = ("report", "heard", "play", "flag", "meter", "ledger", "stats", "admin", "rejected", "catalogue")
LEVELS = ("info", "warn", "error")
KEEP_DAYS = 14


def record(conn: psycopg.Connection, kind: str, message: str, level: str = "info", *, meter_id: Optional[str] = None,
           venue_id: Optional[str] = None, song_id: Optional[str] = None, actor: Optional[str] = None,
           detail: Optional[dict[str, Any]] = None) -> None:
    try:
        with conn.transaction():   # a savepoint inside a caller's transaction; its own transaction otherwise
            conn.execute("""INSERT INTO activity_log (kind, level, meter_id, venue_id, song_id, actor, message, detail)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                         (kind, level, meter_id, venue_id, song_id, actor, message[:500],
                          Jsonb(detail) if detail else None))
    except psycopg.Error as e:   # e.g. the table does not exist yet during a migration
        log.warning("activity not recorded (%s): %s", kind, e)


def _venue(conn, venue_id: Optional[str]) -> str:
    if not venue_id:
        return "an unknown bar"
    r = conn.execute("SELECT name, city FROM venues WHERE venue_id = %s", (venue_id,)).fetchone()
    return f"{r['name']}, {r['city']}" if r and r["name"] else venue_id


def from_event(conn: psycopg.Connection, event: str, d: dict[str, Any]) -> None:
    """Called by db.notify for every live-feed event."""
    if event == "batch":
        record(conn, "report", f"{d.get('meter_id')} sent report #{d.get('seq')}"
               + (" (late: an older window, sent after a gap)" if d.get("late") else ""),
               meter_id=d.get("meter_id"), venue_id=d.get("venue_id"), actor=d.get("meter_id"),
               detail={"seq": d.get("seq"), "window_start": d.get("window_start"), "late": bool(d.get("late"))})
    elif event == "match" and d.get("accepted"):
        record(conn, "heard", f"{d.get('meter_id')} heard “{d.get('title') or d.get('song_id')}” ({d.get('song_id')})",
               meter_id=d.get("meter_id"), venue_id=d.get("venue_id"), song_id=d.get("song_id"), actor="matcher",
               detail={"window_start": d.get("window_start"), "offset_s": d.get("offset_s"), "confidence": d.get("confidence")})
    elif event == "play":
        record(conn, "play", f"Play logged: “{d.get('title') or d.get('song_id')}” by {d.get('artist_name') or '?'} "
               f"at {_venue(conn, d.get('venue_id'))}",
               venue_id=d.get("venue_id"), song_id=d.get("song_id"), actor="play logger",
               detail={"play_id": d.get("play_id"), "started_at": d.get("started_at"), "source": d.get("source")})
    elif event == "flag":
        record(conn, "flag", f"Flag {d.get('type')}: {d.get('detail') or ''}".strip(), "warn",
               meter_id=d.get("meter_id"), venue_id=d.get("venue_id"), song_id=d.get("song_id"), actor="server",
               detail={"flag_id": d.get("flag_id"), "type": d.get("type")})
    elif event == "ledger":
        if d.get("intact"):
            record(conn, "ledger", "Play log check: intact", actor="scheduler")
        else:
            record(conn, "ledger", f"Play log BROKEN at play {d.get('broken_at_play_id')}: results are withheld until it is restored",
                   "error", actor="scheduler", detail={"broken_at_play_id": d.get("broken_at_play_id")})
    # "stats" events: routine recomputes (every 15 s after new plays) are not logged; an admin's recompute is
    # logged by the admin-action middleware ("Admin recomputed the shares").
    # "meter" events: the ingest sends one with every report (online=true); the scheduler records real changes itself


REJECTED = {"unknown_meter": ("warn", "a meter the server does not know"),
            "bad_signature": ("error", "the signature does not match the meter's key (possible fake report)"),
            "seq_conflict": ("error", "a different report with the same number was already stored"),
            "admin_token_required": ("warn", "adding a meter or changing its key needs the admin password"),
            "invalid": ("warn", "the request is not valid"),
            "meter_retired": ("warn", "this meter was retired by SONACAM"),
            "rejected": ("warn", "SONACAM rejected this meter"), "retired": ("warn", "this meter was retired by SONACAM"),
            "meter_id_taken": ("warn", "another meter already uses this id"),
            "too_many_requests": ("warn", "too many meters are waiting for approval")}


REPEAT_S = 60   # the same refusal (same sender, request type and reason) is written once a minute, not per request


def rejected(conn, endpoint: str, body: Any, code: int, error: str, detail: Any = None) -> None:
    level, why = REJECTED.get(error, ("warn", error))
    mid = body.get("meter_id") if isinstance(body, dict) else None
    try:                       # flood guard: a broken or hostile sender cannot fill the log (and the disk)
        if conn.execute(f"""SELECT 1 FROM activity_log WHERE kind = 'rejected' AND coalesce(meter_id, '') = %s
                              AND detail->>'endpoint' = %s AND detail->>'error' = %s
                              AND at > now() - interval '{REPEAT_S} seconds' LIMIT 1""",
                        (str(mid or "")[:40], endpoint, error)).fetchone():
            return
    except psycopg.Error as e:
        log.warning("repeat check skipped: %s", e)
    seq = body.get("seq") if isinstance(body, dict) else None
    record(conn, "rejected", f"Refused {endpoint}{f' #{seq}' if seq is not None else ''} from {mid or 'an unknown sender'}: {why}",
           level, meter_id=mid, venue_id=body.get("venue_id") if isinstance(body, dict) else None, actor=mid,
           detail={"endpoint": endpoint, "http": code, "error": error, "detail": str(detail)[:300] if detail else None})


def prune(conn) -> int:
    return conn.execute(f"DELETE FROM activity_log WHERE at < now() - interval '{KEEP_DAYS} days'").rowcount


def query(conn, kinds: Optional[list[str]] = None, level: Optional[str] = None, meter_id: Optional[str] = None,
          venue_id: Optional[str] = None, q: Optional[str] = None, after_id: Optional[int] = None,
          before_id: Optional[int] = None, limit: int = 200) -> list[dict]:
    where, args = ["true"], []
    if kinds:
        where.append("kind = ANY(%s)"); args.append(kinds)
    if level:
        where.append("level = ANY(%s)"); args.append(["warn", "error"] if level == "warn" else [level])
    if meter_id:
        where.append("meter_id = %s"); args.append(meter_id)
    if venue_id:
        where.append("venue_id = %s"); args.append(venue_id)
    if q:
        where.append("(message ILIKE %s OR song_id ILIKE %s)"); args += [f"%{q}%", f"%{q}%"]
    if after_id is not None:
        where.append("id > %s"); args.append(after_id)
    if before_id is not None:
        where.append("id < %s"); args.append(before_id)
    order = "id ASC" if after_id is not None else "id DESC"
    rows = conn.execute(f"""SELECT id, at, kind, level, meter_id, venue_id, song_id, actor, message, detail
                            FROM activity_log WHERE {' AND '.join(where)} ORDER BY {order} LIMIT %s""",
                        (*args, limit)).fetchall()
    return rows if after_id is None else rows[::-1]   # always newest first
