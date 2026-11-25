"""Ledger endpoints. Contract §6: GET /api/v1/ledger/status. Additive (contract/CHANGES.md): GET /api/v1/ledger/anchors
(Trust tab: last anchors list) and POST /api/v1/ledger/anchor (anchor the current hour now — demo "on demand")."""
from __future__ import annotations

import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool

from fairplay_core.schema import format_utc
from server.api.admin import require_admin
from server.db import connect
from server.ledger import audit
from server.ledger.anchor import anchor_hour

router = APIRouter(prefix="/api/v1/ledger")
_last = {"t": 0.0, "body": None}


def _status() -> dict:
    if _last["body"] is not None and time.monotonic() - _last["t"] < 1.0:     # cache 1 s
        return _last["body"]
    with connect() as conn:
        body = audit.status(conn)
    _last.update(t=time.monotonic(), body=body)
    return body


@router.get("/status")
async def ledger_status():
    return await run_in_threadpool(_status)


def _anchors(limit: int) -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT hour, root, n_plays, via, tx_ref, created_at FROM anchors ORDER BY hour DESC LIMIT %s",
                            (limit,)).fetchall()
    return [{**r, "hour": format_utc(r["hour"]), "created_at": format_utc(r["created_at"])} for r in rows]


@router.get("/anchors")
async def ledger_anchors(limit: int = 24):
    return await run_in_threadpool(_anchors, min(max(limit, 1), 500))


def _anchor_now() -> dict:
    with connect(autocommit=True) as conn, conn.transaction():
        row = anchor_hour(conn, datetime.now(timezone.utc))
    _last["body"] = None
    if row is None:
        return {"ok": False, "detail": "no plays in the current hour yet"}
    return {"ok": True, "hour": format_utc(row["hour"]), "root": row["root"], "n_plays": row["n_plays"],
            "via": row["via"], "tx_ref": row["tx_ref"]}


@router.post("/anchor", dependencies=[Depends(require_admin)])
async def ledger_anchor_now():
    return await run_in_threadpool(_anchor_now)
