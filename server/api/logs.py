"""Activity log for SONACAM admins (D-024): GET /api/v1/admin/activity (JSON) and /api/v1/admin/activity.csv.

Both need the admin password (header X-Admin-Token). Filters: kind (comma list), level (info | warn = warn+error |
error), meter_id, venue_id, q (text search), after_id (newer lines, for live polling), before_id (older lines, paging).
The admin actions themselves (done or refused) are recorded by the middleware in main.py through `admin_action`.
"""
from __future__ import annotations

import csv
import io
import re
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import PlainTextResponse

from fairplay_core.schema import format_utc
from server import activity
from server.api.admin import require_admin
from server.db import connect

router = APIRouter(prefix="/api/v1/admin", dependencies=[Depends(require_admin)])


def _rows(kind, level, meter_id, venue_id, q, after_id, before_id, limit) -> list[dict]:
    kinds = [k for k in (kind or "").split(",") if k in activity.KINDS] or None
    with connect() as c:
        rows = activity.query(c, kinds, level, meter_id, venue_id, q, after_id, before_id, limit)
    return [{**r, "at": format_utc(r["at"])} for r in rows]


@router.get("/activity")
async def admin_activity(kind: Optional[str] = None, level: Optional[str] = Query(None, pattern="^(info|warn|error)$"),
                         meter_id: Optional[str] = None, venue_id: Optional[str] = None, q: Optional[str] = None,
                         after_id: Optional[int] = None, before_id: Optional[int] = None,
                         limit: int = Query(200, ge=1, le=1000)):
    rows = await run_in_threadpool(_rows, kind, level, meter_id, venue_id, q, after_id, before_id, limit)
    return {"rows": rows, "kinds": list(activity.KINDS), "keep_days": activity.KEEP_DAYS,
            "next_before_id": rows[-1]["id"] if len(rows) == limit else None}


@router.get("/activity.csv", response_class=PlainTextResponse)
async def admin_activity_csv(kind: Optional[str] = None, level: Optional[str] = Query(None, pattern="^(info|warn|error)$"),
                             meter_id: Optional[str] = None, venue_id: Optional[str] = None, q: Optional[str] = None):
    rows = await run_in_threadpool(_rows, kind, level, meter_id, venue_id, q, None, None, 50000)
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(["id", "time_utc", "kind", "level", "meter_id", "venue_id", "song_id", "actor", "message"])
    for r in rows:
        w.writerow([r["id"], r["at"], r["kind"], r["level"], r["meter_id"] or "", r["venue_id"] or "", r["song_id"] or "",
                    r["actor"] or "", r["message"]])
    return PlainTextResponse(out.getvalue(), media_type="text/csv",
                             headers={"Content-Disposition": 'attachment; filename="fair_play_activity.csv"'})


# ---------- admin actions, recorded by the middleware in main.py ----------
# (path pattern, what was done, what was attempted, kind, actor)
ACTIONS = [(re.compile(r"^/api/v1/demo/reset$"), "reset the live demo data", "reset the live demo data", "admin", "admin"),
           (re.compile(r"^/api/v1/stats/run$"), "recomputed the shares", "recompute the shares", "admin", "admin"),
           (re.compile(r"^/api/v1/ledger/anchor$"), "anchored the current hour", "anchor the current hour", "admin", "admin"),
           (re.compile(r"^/api/v1/songs/(?P<song>[^/]+)/approve$"), "approved song {song}", "approve song {song}", "admin", "admin"),
           (re.compile(r"^/api/v1/songs$"), "uploaded a song to the catalogue", "upload a song", "catalogue", "uploader")]


def admin_action(path: str, query: dict, status: int, client: Optional[str]) -> None:
    for rx, done, tried, kind, actor in ACTIONS:
        m = rx.match(path)
        if not m:
            continue
        g = m.groupdict()
        done, tried = done.format(**g), tried.format(**g)
        extra = ", ".join(f"{k}: {v}" for k, v in query.items() if k in ("period", "mode", "reason"))
        detail = {"path": path, "http": status, **{k: v for k, v in query.items() if k != "confirm"}}
        with connect(autocommit=True) as c:
            if status == 403:
                activity.record(c, "admin", f"Refused: an attempt to {tried} without the right admin password", "warn",
                                actor=client or "unknown", song_id=g.get("song"), detail=detail)
            elif status < 400:
                who = "Admin" if actor == "admin" else "Someone"
                activity.record(c, kind, f"{who} {done}" + (f" ({extra})" if extra else ""),
                                "warn" if path.endswith("/reset") else "info", actor=actor, song_id=g.get("song"), detail=detail)
            else:
                activity.record(c, kind, f"Could not {tried} (HTTP {status})", "error", actor=actor,
                                song_id=g.get("song"), detail=detail)
        return
