"""GET /api/v1/feed — live Server-Sent Events (contract §6.1). Keep-alive comment every 15 s."""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from server.api.events import bus

router = APIRouter()


@router.get("/api/v1/feed")
async def feed(request: Request):
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
                yield {"event": ev.get("event", "message"), "data": json.dumps(ev.get("data", {}), ensure_ascii=False)}
        finally:
            bus.unsubscribe(q)

    return EventSourceResponse(stream(), ping=15)
