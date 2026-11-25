"""GET /api/v1/feed — live Server-Sent Events (contract §6.1). Keep-alive comment every 15 s."""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from server.api.events import bus

router = APIRouter()


PUBLIC_PLAY_KEYS = ("song_id", "title", "artist_name", "city", "started_at", "source")


def _public(ev: dict):
    """D-028: what someone not signed in as SONACAM may see live — plays as song, artist and city (never the bar or
    the meter), and the play-log / recompute signals. Reports, matches, flags and meter events are SONACAM-only."""
    kind, data = ev.get("event"), ev.get("data") or {}
    if kind == "play":
        if data.get("artist_name") == "Fair Play test artist":
            return None
        return {"event": "play", "data": {k: data.get(k) for k in PUBLIC_PLAY_KEYS}}
    if kind == "ledger":
        return {"event": "ledger", "data": {"intact": data.get("intact")}}
    if kind == "stats":
        return {"event": "stats", "data": {"period": data.get("period"), "mode": data.get("mode")}}
    return None


@router.get("/api/v1/feed")
async def feed(request: Request):
    from fastapi.concurrency import run_in_threadpool
    from server.api.admin import is_sonacam
    sonacam = await run_in_threadpool(is_sonacam, request, request.headers.get("x-admin-token"))
    q = bus.subscribe()

    async def stream():
        try:
            while True:
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    if await request.is_disconnected():
                        break
                    continue
                if not sonacam:
                    ev = _public(ev)
                    if ev is None:
                        continue
                yield {"event": ev.get("event", "message"), "data": json.dumps(ev.get("data", {}), ensure_ascii=False)}
        finally:
            bus.unsubscribe(q)

    return EventSourceResponse(stream(), ping=15)
