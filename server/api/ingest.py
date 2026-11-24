"""Device endpoints (contract §4): POST /v1/batches, /v1/batches/bulk, /v1/heartbeat, /v1/meters/register."""
from __future__ import annotations

import json
from typing import Any, Callable

from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from server import ingest
from server.db import connect
from server.registry import upsert_meter

router = APIRouter(prefix="/v1")


async def _json_body(request: Request) -> Any:
    try:
        return json.loads(await request.body())
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def _with_conn(fn: Callable, body: Any) -> ingest.Result:
    with connect(autocommit=True, retries=3) as conn:   # each check/store runs in its own explicit transaction
        return fn(conn, body)


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


def _register(conn, body) -> ingest.Result:
    if not isinstance(body, dict):
        return ingest.Result(422, {"error": "invalid", "detail": "body must be a .pub.json object"})
    try:
        with conn.transaction():
            r = upsert_meter(conn, body)
    except (ValueError, KeyError) as e:
        return ingest.Result(422, {"error": "invalid", "detail": str(e)})
    return ingest.Result(200, {"ok": True, **r})


@router.post("/meters/register")
async def register_meter(request: Request):
    """Admin convenience (demo: no auth). Same as dropping a .pub.json into contract/meters and restarting."""
    return await _handle(_register, request)
