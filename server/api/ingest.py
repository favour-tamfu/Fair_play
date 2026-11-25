"""Device endpoints (contract §4): POST /v1/batches, /v1/batches/bulk, /v1/heartbeat, /v1/calibration, /v1/meters/register."""
from __future__ import annotations

import json
from typing import Any, Callable

from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from server import activity, config, ingest
from server.api.admin import HEADER, register_allowed_without_token, token_ok
from server.db import connect
from server.registry import upsert_meter

router = APIRouter(prefix="/v1")


async def _json_body(request: Request) -> Any:
    try:
        return json.loads(await request.body())
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


ENDPOINT = {"ingest_batch": "report", "ingest_bulk": "report", "ingest_heartbeat": "heartbeat",
            "ingest_calibration": "calibration", "<lambda>": "meter registration", "request_join": "meter join request"}   # register is wrapped in a lambda


def _with_conn(fn: Callable, body: Any, *extra) -> ingest.Result:
    with connect(autocommit=True, retries=3) as conn:   # each check/store runs in its own explicit transaction
        r = fn(conn, body, *extra)
        what = ENDPOINT.get(getattr(fn, "__name__", ""), "device request")
        if r.code >= 400:                                 # D-024: refused requests go to the admins' activity log
            activity.rejected(conn, what, body, r.code, r.body.get("error", "error"), r.body.get("detail"))
        elif fn is ingest.ingest_bulk:
            for item, res in zip(body.get("batches", []) if isinstance(body, dict) else [], r.body.get("results", [])):
                if res.get("status") == "error":
                    activity.rejected(conn, what, item, 400, res.get("error", "error"))
        return r


async def _handle(fn: Callable, request: Request) -> JSONResponse:
    body = await _json_body(request)
    if body is None:
        return JSONResponse({"error": "invalid", "detail": "body is not valid JSON"}, status_code=422)
    r = await run_in_threadpool(_with_conn, fn, body)
    return JSONResponse(r.body, status_code=r.code)


@router.post("/batches")
async def post_batch(request: Request):
    return await _handle(ingest.ingest_batch, request)


@router.post("/batches/bulk")
async def post_bulk(request: Request):
    return await _handle(ingest.ingest_bulk, request)


@router.post("/heartbeat")
async def post_heartbeat(request: Request):
    return await _handle(ingest.ingest_heartbeat, request)


@router.post("/calibration")
async def post_calibration(request: Request):
    """Contract §4: {"ok":true} (+ run_id, matched, total, catch_rate, applied, pending_windows — B-T14)."""
    from server.calibration import ingest_calibration
    return await _handle(ingest_calibration, request)


def _register(conn, body, admin: bool = False) -> ingest.Result:
    if not isinstance(body, dict):
        return ingest.Result(422, {"error": "invalid", "detail": "body must be a .pub.json object"})
    if not admin and not register_allowed_without_token(conn, body):
        return ingest.Result(403, {"error": "admin_token_required",
                                   "detail": f"adding a meter or changing its key needs the {HEADER} header"})
    try:
        with conn.transaction():
            r = upsert_meter(conn, body)
            if admin:                                   # D-029: re-registered by SONACAM: no longer retired
                conn.execute("UPDATE meters SET retired_at = NULL WHERE meter_id = %s", (r["meter_id"],))
    except (ValueError, KeyError) as e:
        return ingest.Result(422, {"error": "invalid", "detail": str(e)})
    return ingest.Result(200, {"ok": True, **r})


@router.post("/meters/join")
async def join_meter(request: Request):
    """A new meter asks to join, signed with its own key; SONACAM approves it on the operations page (server/joins.py).
    The meter re-sends the same request to learn its status: 202 pending, 200 approved, 403 rejected/retired."""
    from server.joins import request_join
    return await _handle(request_join, request)


@router.post("/meters/register")
async def register_meter(request: Request):
    """Same as dropping a .pub.json into contract/meters and restarting. Adding a meter or changing a key needs the
    admin token (D-020); re-sending a meter's current key, or a key that matches contract/meters, is always fine."""
    # a signed-in SONACAM user (the admin page, D-028) or the X-Admin-Token header (scripts)
    from server.api.admin import is_sonacam
    admin = bool(config.ADMIN_TOKEN) and await run_in_threadpool(is_sonacam, request, request.headers.get(HEADER))
    body = await _json_body(request)
    if body is None:
        return JSONResponse({"error": "invalid", "detail": "body is not valid JSON"}, status_code=422)
    r = await run_in_threadpool(_with_conn, lambda conn, b: _register(conn, b, admin or not config.ADMIN_TOKEN), body)
    return JSONResponse(r.body, status_code=r.code)
