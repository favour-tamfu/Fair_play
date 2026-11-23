"""Fair Play API (the "front desk"). B-T02: skeleton with /health; routes are added in B-T03 onwards.

    uvicorn server.api.main:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool

from fairplay_core.schema import format_utc
from server import config
from server.db import connect, ping
from server.db.migrate import migrate

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("fairplay.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    applied = await run_in_threadpool(migrate)
    log.info("startup: migrations applied now: %s", applied or "none (up to date)")
    yield


app = FastAPI(title="Fair Play — SONACAM server", version=config.VERSION, lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    """Pulse check used by A's netcheck/clockcheck: is the API up, is the db reachable, what time is it here."""
    try:
        with connect(retries=1) as conn:
            db_ok = ping(conn)
    except Exception:  # db down must not break /health
        db_ok = False
    return {"ok": True, "server_time": format_utc(datetime.now(timezone.utc)), "db": db_ok, "version": config.VERSION}
