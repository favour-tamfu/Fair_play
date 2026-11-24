"""POST /api/v1/stats/run?period=live&mode=both — recompute shares now (contract §6)."""
from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.concurrency import run_in_threadpool

from server.db import connect
from server.stats.run import run_both, run_stats

router = APIRouter(prefix="/api/v1")


def _run(period: str, mode: str) -> dict:
    with connect(autocommit=True) as c:
        return run_both(c, period) if mode == "both" else run_stats(c, period, mode)


@router.post("/stats/run")
async def stats_run(period: str = Query("live", pattern="^(live|mock_month|all)$"),
                    mode: str = Query("both", pattern="^(both|standardised|raw)$")):
    """Answer: {"stats_run_id","status":"done","duration_ms"} (+ period, mode, n_plays, n_songs, n_flags;
    with mode=both: the standardised run's id, raw_stats_run_id, total duration)."""
    return await run_in_threadpool(_run, period, mode)


def _reset(reason: str) -> dict:
    from server.demo import reset_live
    with connect(autocommit=True) as c:
        out = reset_live(c, reason)
        out["stats_run_id"] = run_both(c, "live")["stats_run_id"]     # empty live run -> SSE "stats": pages refresh
    return out


@router.post("/demo/reset")
async def demo_reset(confirm: str = Query(..., pattern="^yes$"), reason: str = Query("demo reset", max_length=200)):
    """Wipe the LIVE test data (plays, batches, matches, windows, live stats) and start a new live-chain epoch.
    Keeps the catalogue, meters and the mock month (D-017). Requires ?confirm=yes."""
    return await run_in_threadpool(_reset, reason)
