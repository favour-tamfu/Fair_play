"""SONACAM operations (D-029), SONACAM only.

GET  /api/v1/admin/meters                 every real/test meter (and, with ?mock=1, the mock-month bars): bar, city,
                                          online, last seen, queued, catch rate, key fingerprint, retired
POST /api/v1/admin/meters/{id}/retire     retire a meter: its reports are refused from now on (re-register to restore)
POST /api/v1/flags/{flag_id}/review       {"reviewed": true|false, "note": "..."} mark a review flag as (not) reviewed
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from fairplay_core.schema import format_utc
from server import activity, config
from server.api.admin import current_user, require_admin
from server.db import connect

router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_admin)])


def key_fingerprint(key_b64: Optional[str]) -> str:
    """Short, comparable fingerprint of a meter's public key (what the meter printed at setup is the full key)."""
    if not key_b64:
        return ""
    h = hashlib.sha256(key_b64.encode()).hexdigest()[:16]
    return " ".join(h[i:i + 4] for i in range(0, 16, 4))


def _meters(include_mock: bool) -> list[dict]:
    now = datetime.now(timezone.utc)
    with connect() as c:
        rows = c.execute("""SELECT m.*, v.name AS venue_name, v.city FROM meters m LEFT JOIN venues v USING (venue_id)
                            WHERE %s OR m.source <> 'mock' ORDER BY m.meter_id""", (include_mock,)).fetchall()
    out = []
    for m in rows:
        online = (m["source"] != "mock" and m["retired_at"] is None and m["last_seen"] is not None
                  and (now - m["last_seen"]).total_seconds() <= config.METER_OFFLINE_S)
        out.append({"meter_id": m["meter_id"], "venue_id": m["venue_id"], "bar": m["venue_name"] or m["venue_id"],
                    "city": m["city"], "source": m["source"], "online": online,
                    "last_seen": format_utc(m["last_seen"]) if m["last_seen"] else None, "queued": int(m["queued"] or 0),
                    "catch_rate": float(m["catch_rate"]) if m["catch_rate"] is not None else None,
                    "key_fingerprint": key_fingerprint(m["public_key_b64"]),
                    "retired_at": format_utc(m["retired_at"]) if m["retired_at"] else None})
    return out


@router.get("/admin/meters")
async def admin_meters(mock: bool = False):
    return await run_in_threadpool(_meters, mock)


def _retire(meter_id: str, who: str) -> dict:
    with connect(autocommit=True) as c:
        r = c.execute("UPDATE meters SET retired_at = now() WHERE meter_id = %s AND retired_at IS NULL RETURNING meter_id, venue_id",
                      (meter_id,)).fetchone()
        if r is None:
            exists = c.execute("SELECT 1 FROM meters WHERE meter_id = %s", (meter_id,)).fetchone()
            if not exists:
                raise HTTPException(404, detail="unknown meter")
            return {"meter_id": meter_id, "retired": True, "changed": False}
        activity.record(c, "meter", f"{meter_id} retired by {who}: its reports are refused from now on", "warn",
                        meter_id=meter_id, venue_id=r["venue_id"], actor=who)
    return {"meter_id": meter_id, "retired": True, "changed": True}


@router.post("/admin/meters/{meter_id}/retire")
async def retire_meter(meter_id: str, request: Request):
    u = await run_in_threadpool(current_user, request)
    return await run_in_threadpool(_retire, meter_id, (u or {}).get("name") or "admin")


class Review(BaseModel):
    reviewed: bool = True
    note: Optional[str] = None


def _review(flag_id: int, body: Review, who: str) -> dict:
    with connect(autocommit=True) as c:
        r = c.execute("""UPDATE flags SET reviewed_at = CASE WHEN %s THEN now() END, reviewed_by = CASE WHEN %s THEN %s END,
                                         review_note = %s WHERE flag_id = %s RETURNING flag_id, type, venue_id, song_id""",
                      (body.reviewed, body.reviewed, who, (body.note or None) and body.note[:300], flag_id)).fetchone()
        if r is None:
            raise HTTPException(404, detail="unknown flag")
        activity.record(c, "flag", f"Flag {r['type']} #{flag_id} marked {'reviewed' if body.reviewed else 'not reviewed'} by {who}"
                        + (f": {body.note[:120]}" if body.note else ""), venue_id=r["venue_id"], song_id=r["song_id"], actor=who)
    return {"flag_id": flag_id, "reviewed": body.reviewed}


@router.post("/flags/{flag_id}/review")
async def review_flag(flag_id: int, body: Review, request: Request):
    u = await run_in_threadpool(current_user, request)
    return await run_in_threadpool(_review, flag_id, body, (u or {}).get("name") or "admin")
