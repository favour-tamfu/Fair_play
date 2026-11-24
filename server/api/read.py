"""Read API v1 for the web front-end (contract §6). Every response matches contract/schemas (tests check it).

Query params: period = live | mock_month | all (default all); mode = standardised | raw (default standardised).
  live       = plays from live/virtual meters since config.LIVE_SINCE
  mock_month = plays imported from A's mock month (source mock, B-T11)
Weights, shares and amounts come from the latest finished stats run for (period, mode). Before any stats run:
plays have weight null, plays_counted = plays_raw (nothing standardised yet), shares/payouts/compare-flat are
empty-but-valid. Plays superseded by a correction are never shown or counted.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.concurrency import run_in_threadpool

from fairplay_core.schema import format_utc, parse_utc
from server import config
from server.db import connect
from server.ledger import audit
from server.money import largest_remainder
from server.stats import compare
from server.stats.periods import ACTIVE, period_sql

router = APIRouter(prefix="/api/v1")
PERIOD = Query("all", pattern="^(live|mock_month|all)$")
MODE = Query("standardised", pattern="^(standardised|raw)$")


# --------------------------------------------------------------------------- helpers

def latest_run(conn, period: str, mode: str) -> Optional[dict]:
    return conn.execute("""SELECT * FROM stats_runs WHERE period = %s AND mode = %s AND finished_at IS NOT NULL
                           ORDER BY finished_at DESC LIMIT 1""", (period, mode)).fetchone()


def _ts(v: Optional[datetime]) -> Optional[str]:
    return format_utc(v) if v else None


def play_out(r: dict) -> dict:
    return {"play_id": r["play_id"], "venue_id": r["venue_id"], "meter_id": r["meter_id"], "song_id": r["song_id"],
            "title": r["title"] or r["song_id"], "artist_name": r["artist_name"] or "", "started_at": _ts(r["started_at"]),
            "duration_s": float(r["duration_s"] or 0), "source": r["source"],
            "weight": None if r["weight"] is None else float(r["weight"]), "reasons": list(r["reasons"] or [])}


def query_plays(conn, period: str, mode: str, venue_id=None, song_id=None, artist=None, limit=50) -> list[dict]:
    where, args = period_sql(period)
    run = latest_run(conn, period, mode)
    sql = f"""SELECT p.play_id, p.venue_id, p.meter_id, p.song_id, p.started_at, p.source,
                     COALESCE(x.duration_s, p.duration_s) AS duration_s, s.title, s.artist_name, w.weight, w.reasons
              FROM plays p LEFT JOIN play_extents x USING (play_id) LEFT JOIN songs s USING (song_id)
              LEFT JOIN play_weights w ON w.play_id = p.play_id AND w.stats_run_id = %s
              WHERE {ACTIVE} AND {where}"""
    args = [run["stats_run_id"] if run else None] + args
    for col, val in (("p.venue_id", venue_id), ("p.song_id", song_id), ("s.artist_name", artist)):
        if val:
            sql += f" AND {col} = %s"
            args.append(val)
    sql += " ORDER BY p.started_at DESC, p.seq_no DESC LIMIT %s"
    args.append(limit)
    return [play_out(r) for r in conn.execute(sql, args)]


def share_rows(conn, period: str, mode: str, pot: int) -> tuple[Optional[dict], list[dict], float]:
    run = latest_run(conn, period, mode)
    if run is None:
        return None, [], 0.0
    rows = conn.execute("""SELECT sh.*, s.title, s.artist_name FROM shares sh LEFT JOIN songs s USING (song_id)
                           WHERE sh.stats_run_id = %s ORDER BY sh.share DESC, sh.song_id""",
                        (run["stats_run_id"],)).fetchall()
    amounts = largest_remainder(pot, [r["share"] for r in rows])
    out = [{"song_id": r["song_id"], "title": r["title"] or r["song_id"], "artist_name": r["artist_name"] or "",
            "raw_plays": int(r["raw_plays"] or 0), "weighted_plays": float(r["weighted_plays"] or 0),
            "share": float(r["share"]), "ci_low": float(r["ci_low"] or 0), "ci_high": float(r["ci_high"] or 0),
            "amount_fcfa": a, "flags": list(r["flags"] or [])} for r, a in zip(rows, amounts)]
    return run, out, 0.0                       # D-011: unidentified music is not recorded -> no escrow


# --------------------------------------------------------------------------- endpoints (sync bodies run in a thread)

def _overview(period: str) -> dict:
    where, args = period_sql(period)
    now = datetime.now(timezone.utc)
    with connect() as c:
        m = c.execute("""SELECT count(*) AS total, count(*) FILTER (WHERE source <> 'mock' AND last_seen > %s) AS online
                         FROM meters""", (now - timedelta(seconds=config.METER_OFFLINE_S),)).fetchone()
        n_venues = c.execute("SELECT count(*) AS n FROM venues").fetchone()["n"]
        raw = c.execute(f"SELECT count(*) AS n FROM plays p WHERE {ACTIVE} AND {where}", args).fetchone()["n"]
        run = latest_run(c, period, "standardised")
        counted = float(raw)
        if run:
            counted = float(c.execute(f"""SELECT COALESCE(sum(w.weight), 0) AS s FROM plays p JOIN play_weights w
                                         ON w.play_id = p.play_id AND w.stats_run_id = %s WHERE {ACTIVE} AND {where}""",
                                      [run["stats_run_id"]] + args).fetchone()["s"])
        ready = c.execute("SELECT count(*) AS n FROM songs WHERE status = 'ready'").fetchone()["n"]
        led = audit.status(c)
    return {"meters_online": m["online"], "meters_total": m["total"], "venues": n_venues, "plays_raw": raw,
            "plays_counted": round(counted, 2), "songs_ready": ready, "unidentified_music_min": 0.0,
            "rule_version": config.RULE_VERSION, "ledger_intact": led["intact"], "last_anchor": led["last_anchor"]}


@router.get("/overview")
async def overview(period: str = PERIOD):
    return await run_in_threadpool(_overview, period)


def _venues() -> list[dict]:
    now = datetime.now(timezone.utc)
    with connect() as c:
        vs = c.execute("SELECT * FROM venues ORDER BY venue_id").fetchall()
        ms = c.execute("SELECT * FROM meters ORDER BY meter_id").fetchall()
    out = []
    for v in vs:
        meters = [{"meter_id": m["meter_id"],
                   "online": m["source"] != "mock" and m["last_seen"] is not None
                   and (now - m["last_seen"]).total_seconds() <= config.METER_OFFLINE_S,
                   "last_seen": _ts(m["last_seen"]), "queued": int(m["queued"] or 0),
                   "catch_rate": float(m["catch_rate"] if m["catch_rate"] is not None else 0.8)}
                  for m in ms if m["venue_id"] == v["venue_id"]]
        out.append({"venue_id": v["venue_id"], "name": v["name"] or v["venue_id"], "city": v["city"], "lat": v["lat"],
                    "lon": v["lon"], "stratum": v["stratum"], "bars_in_stratum": v["bars_in_stratum"], "meters": meters})
    return out


@router.get("/venues")
async def venues():
    return await run_in_threadpool(_venues)


def _plays(period, mode, venue_id, song_id, limit) -> list[dict]:
    with connect() as c:
        return query_plays(c, period, mode, venue_id, song_id, limit=limit)


@router.get("/plays")
async def plays(period: str = PERIOD, mode: str = MODE, venue_id: Optional[str] = None, song_id: Optional[str] = None,
                limit: int = Query(50, ge=1, le=1000)):
    return await run_in_threadpool(_plays, period, mode, venue_id, song_id, limit)


def _shares(period: str, mode: str) -> dict:
    with connect() as c:
        run, rows, escrow = share_rows(c, period, mode, config.POT_DEFAULT_FCFA)
    pot = int((run["params"] or {}).get("pot_fcfa", config.POT_DEFAULT_FCFA)) if run else config.POT_DEFAULT_FCFA
    return {"stats_run_id": run["stats_run_id"] if run else None,
            "rule_version": (run["rule_version"] if run else config.RULE_VERSION) if mode == "standardised" else "raw",
            "pot_fcfa": pot, "escrow_share": escrow, "rows": rows}


@router.get("/shares")
async def shares(period: str = PERIOD, mode: str = MODE):
    return await run_in_threadpool(_shares, period, mode)


def _flags(period: str) -> list[dict]:
    # stats flags of this period's runs + flags not from a stats run (e.g. duplicate_suspected from the catalogue)
    sql = """SELECT flag_id, type, song_id, venue_id, detail, created_at FROM flags
             WHERE stats_run_id IN (SELECT stats_run_id FROM stats_runs WHERE period = %s)
                OR (stats_run_id IS NULL AND created_at >= %s)"""
    since = parse_utc(config.LIVE_SINCE) if period == "live" else datetime(1970, 1, 1, tzinfo=timezone.utc)
    args = [period, since]
    with connect() as c:
        rows = c.execute(sql + " ORDER BY created_at DESC, flag_id DESC LIMIT 500", args).fetchall()
    return [{**r, "detail": r["detail"] or "", "created_at": format_utc(r["created_at"])} for r in rows]


@router.get("/flags")
async def flags(period: str = PERIOD):
    return await run_in_threadpool(_flags, period)


def _payouts(period: str, pot: int) -> dict:
    """Empty-but-valid until B-T12 (owner splits, statements). `frozen` already follows the ledger."""
    with connect() as c:
        frozen = not audit.status(c)["intact"]
    return {"pot_fcfa": pot, "frozen": frozen, "rows": [], "total_fcfa": 0}


@router.get("/payouts")
async def payouts(period: str = PERIOD, pot: int = Query(config.POT_DEFAULT_FCFA, ge=0)):
    return await run_in_threadpool(_payouts, period, pot)


def _compare_flat(pot: int) -> dict:
    with connect() as c:
        return compare.compare_flat(c, pot)


@router.get("/compare-flat")
async def compare_flat(pot: int = Query(config.POT_DEFAULT_FCFA, ge=0)):
    """Flat split vs Fair Play against the mock month truth (B-T11, brief §7.4); n_artists = 0: not computed yet."""
    return await run_in_threadpool(_compare_flat, pot)


def _artists() -> list[dict]:
    with connect() as c:
        rows = c.execute("""SELECT artist_name, array_agg(song_id ORDER BY song_id) AS songs FROM songs
                            WHERE (status = 'ready' OR source = 'mock') AND artist_name IS NOT NULL
                            GROUP BY artist_name ORDER BY artist_name""").fetchall()
    return [{"artist_name": r["artist_name"], "songs": list(r["songs"])} for r in rows]


@router.get("/artists")
async def artists():
    return await run_in_threadpool(_artists)


def _artist(name: str, period: str, mode: str) -> Optional[dict]:
    where, args = period_sql(period)
    with connect() as c:
        songs = c.execute("""SELECT song_id, title FROM songs WHERE artist_name = %s AND (status = 'ready' OR source = 'mock')
                             ORDER BY song_id""", (name,)).fetchall()
        if not songs:
            return None
        run = latest_run(c, period, mode)
        rid = run["stats_run_id"] if run else None
        base = f"""FROM plays p JOIN songs s USING (song_id) LEFT JOIN venues v ON v.venue_id = p.venue_id
                   LEFT JOIN play_weights w ON w.play_id = p.play_id AND w.stats_run_id = %s
                   WHERE {ACTIVE} AND {where} AND s.artist_name = %s"""
        a = [rid] + args + [name]
        by_venue = c.execute(f"""SELECT p.venue_id, max(v.name) AS name, max(v.city) AS city, count(*) AS plays_raw,
                                 COALESCE(sum(COALESCE(w.weight, 1)), 0) AS plays_counted {base}
                                 GROUP BY p.venue_id ORDER BY count(*) DESC""", a).fetchall()
        by_day = c.execute(f"""SELECT to_char((p.started_at + interval '{config.LOCAL_UTC_OFFSET_H} hour')::date, 'YYYY-MM-DD')
                               AS date, count(*) AS plays_raw, COALESCE(sum(COALESCE(w.weight, 1)), 0) AS plays_counted
                               {base} GROUP BY 1 ORDER BY 1""", a).fetchall()
        _, rows, _ = share_rows(c, period, mode, config.POT_DEFAULT_FCFA)
        recent = query_plays(c, period, mode, artist=name, limit=10)
    ids = {s["song_id"] for s in songs}
    return {"artist_name": name, "songs": songs,
            "plays_by_venue": [{"venue_id": r["venue_id"], "name": r["name"] or r["venue_id"], "city": r["city"],
                                "plays_raw": r["plays_raw"], "plays_counted": float(r["plays_counted"])} for r in by_venue],
            "plays_by_day": [{"date": r["date"], "plays_raw": r["plays_raw"], "plays_counted": float(r["plays_counted"])}
                             for r in by_day],
            "amount_fcfa": sum(r["amount_fcfa"] for r in rows if r["song_id"] in ids), "recent": recent}


@router.get("/artists/{artist_name}")
async def artist(artist_name: str, period: str = PERIOD, mode: str = MODE):
    body = await run_in_threadpool(_artist, artist_name, period, mode)
    if body is None:
        raise HTTPException(404, detail="unknown artist")
    return body
