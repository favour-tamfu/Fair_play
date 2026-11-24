"""Fair Play API (the "front desk").

    uvicorn server.api.main:app --host 0.0.0.0 --port 8000

Start-up: apply migrations → load contract/meters/*.pub.json → start the live-feed listener.
Routes: /health, device ingest (/v1/*), live feed (/api/v1/feed). Read API + static web follow in B-T08.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware

from fairplay_core.schema import format_utc
from server import config
from server.api import feed, ingest, ledger, songs
from server.api.events import bus
from server.db import connect, ping
from server.db.migrate import migrate
from server.registry import load_meter_keys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("fairplay.api")


def _startup() -> None:
    applied = migrate()
    log.info("startup: migrations applied now: %s", applied or "none (up to date)")
    with connect(autocommit=True) as conn, conn.transaction():
        meters = load_meter_keys(conn)
    log.info("startup: meter keys loaded: %s", ", ".join(meters) or "none")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await run_in_threadpool(_startup)
    bus.start(asyncio.get_running_loop())
    yield
    bus.stop()


app = FastAPI(title="Fair Play — SONACAM server", version=config.VERSION, lifespan=lifespan)
# A's web dev server (python -m http.server 8080) may call the API from another origin during development
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:8080", "http://127.0.0.1:8080"],
                   allow_methods=["*"], allow_headers=["*"])
app.include_router(ingest.router)
app.include_router(feed.router)
app.include_router(songs.router)
app.include_router(ledger.router)


@app.get("/health")
def health() -> dict:
    """Pulse check used by A's netcheck/clockcheck: is the API up, is the db reachable, what time is it here."""
    try:
        with connect(retries=1) as conn:
            db_ok = ping(conn)
    except Exception:  # db down must not break /health
        db_ok = False
    return {"ok": True, "server_time": format_utc(datetime.now(timezone.utc)), "db": db_ok, "version": config.VERSION}
