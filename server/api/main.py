"""Fair Play API (the "front desk").

    uvicorn server.api.main:app --host 0.0.0.0 --port 8000

Start-up: apply migrations → load contract/meters/*.pub.json → start the live-feed listener.
Routes: /health, device ingest (/v1/*), catalogue, ledger, read API (/api/v1/*), live feed; A's web/ at /.
"""
from __future__ import annotations

import asyncio
import logging
import mimetypes
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
import psycopg

from fairplay_core.schema import format_utc
from server import config
from server.api import auth_api, feed, ingest, ledger, logs, ops, read, songs, stats
from server.api.events import bus
from server.db import connect, ping
from server.db.migrate import migrate
from server.registry import fill_known_venues, load_meter_keys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("fairplay.api")


def _startup() -> None:
    applied = migrate()
    log.info("startup: migrations applied now: %s", applied or "none (up to date)")
    with connect(autocommit=True) as conn, conn.transaction():
        meters = load_meter_keys(conn)
        venues = fill_known_venues(conn)
        from server.auth import ensure_sonacam_user
        ensure_sonacam_user(conn)            # D-028: the 'sonacam' account follows ADMIN_TOKEN
    log.info("startup: meter keys loaded: %s; known venues filled: %s", ", ".join(meters) or "none", ", ".join(venues))


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
app.include_router(read.router)
app.include_router(stats.router)
app.include_router(logs.router)
app.include_router(auth_api.router)
app.include_router(ops.router)


MAX_DEVICE_BODY = 4 * 1024 * 1024    # a meter sends at most 50 reports at once (well under 1 MB); song uploads are elsewhere


@app.middleware("http")
async def security_headers(request, call_next):
    """Browser protections on every answer, and a size cap on meter requests (refused before the body is read)."""
    if request.url.path.startswith("/v1/"):
        n = request.headers.get("content-length", "")
        if n.isdigit() and int(n) > MAX_DEVICE_BODY:
            return JSONResponse({"error": "too_large", "detail": "request body too large"}, status_code=413)
    response = await call_next(request)
    h = response.headers
    h.setdefault("X-Content-Type-Options", "nosniff")                      # no guessing file types
    h.setdefault("X-Frame-Options", "DENY")                                # no framing: stops click-jacking on Approve
    h.setdefault("Content-Security-Policy", "frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'")
    h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")     # page addresses do not leak to other sites
    h.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")
    if request.headers.get("x-forwarded-proto", "").lower() == "https" or request.url.scheme == "https":
        h.setdefault("Strict-Transport-Security", "max-age=15552000")      # browsers keep using HTTPS
    if request.url.path.startswith("/api/") and "cache-control" not in h:
        h["Cache-Control"] = "no-store"                                    # signed-in data is never cached
    return response


@app.middleware("http")
async def record_admin_actions(request, call_next):
    """D-024: admin actions (done, failed or refused for a wrong password) go to the activity log."""
    response = await call_next(request)
    if request.method == "POST" and request.url.path.startswith("/api/v1/"):
        try:
            await run_in_threadpool(logs.admin_action, request.url.path, dict(request.query_params),
                                    response.status_code, request.client.host if request.client else None)
        except Exception as e:   # never let the log break the action
            log.warning("admin action not recorded: %s", e)
    return response


@app.get("/health")
def health() -> dict:
    """Pulse check used by A's netcheck/clockcheck: is the API up, is the db reachable, what time is it here."""
    try:
        with connect(retries=1) as conn:
            db_ok = ping(conn)
    except Exception:  # db down must not break /health
        db_ok = False
    return {"ok": True, "server_time": format_utc(datetime.now(timezone.utc)), "db": db_ok, "version": config.VERSION}


@app.exception_handler(psycopg.OperationalError)
async def db_unavailable(request, exc):
    """Database restarting / unreachable: a clean 503 the meter (and pages) retry, not a 500 traceback (audit #10)."""
    logging.getLogger("api").warning("db unavailable for %s %s: %s", request.method, request.url.path,
                                     str(exc).splitlines()[0][:120])
    return JSONResponse({"error": "db_unavailable", "detail": "database restarting, please retry"}, status_code=503,
                        headers={"Retry-After": "2"})


mimetypes.add_type("font/woff2", ".woff2")   # web fonts (web/fonts, not in git): the container's table lacks it


class FreshStaticFiles(StaticFiles):
    """Static pages with `Cache-Control: no-cache`: the browser re-checks every file (cheap 304 when unchanged),
    so a page never mixes a new index.html with an old cached app.js / app.css."""

    def file_response(self, *args, **kwargs):
        resp = super().file_response(*args, **kwargs)
        resp.headers["Cache-Control"] = "no-cache"
        return resp


# A's static pages (contract §6.2) — mounted LAST so every API route above takes precedence.
if config.SERVE_WEB and config.WEB_DIR.is_dir():
    app.mount("/", FreshStaticFiles(directory=str(config.WEB_DIR), html=True), name="web")
