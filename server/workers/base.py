"""Shared worker start-up and the job-board loop.

run_jobs(name, kind, handler): take one ticket of `kind` at a time (FOR UPDATE SKIP LOCKED), call handler(conn, job),
mark it done; if the handler raises, mark it error (with the message) and carry on with the next ticket.
Tickets left 'running' by a crashed worker are put back on start-up.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Callable

import psycopg

from server import config
from server.db import connect, jobs, ping
from server.db.migrate import migrate


def setup(name: str) -> logging.Logger:
    logging.basicConfig(level=logging.INFO, format=f"%(asctime)s %(levelname)s {name} %(message)s")
    log = logging.getLogger(name)
    migrate()  # safe if the api is migrating at the same time (advisory lock)
    return log


def run_one(conn: psycopg.Connection, kind: str, handler: Callable[[psycopg.Connection, dict], Any],
            log: logging.Logger) -> bool:
    """Process at most one queued job. Returns True if a job was taken."""
    with conn.transaction():
        job = jobs.claim(conn, kind)
    if job is None:
        return False
    t0 = time.perf_counter()
    try:
        handler(conn, job)
        with conn.transaction():
            jobs.done(conn, job["id"])
        log.info("job %s %s(%s) done in %.0f ms", job["id"], kind, job["ref"], (time.perf_counter() - t0) * 1000)
    except Exception as e:  # never let one bad job stop the worker
        log.exception("job %s %s(%s) failed", job["id"], kind, job["ref"])
        if conn.info.transaction_status != psycopg.pq.TransactionStatus.IDLE:
            conn.rollback()
        with conn.transaction():
            jobs.fail(conn, job["id"], f"{type(e).__name__}: {e}")
    return True


def run_jobs(name: str, kind: str, handler: Callable[[psycopg.Connection, dict], Any]) -> None:
    log = setup(name)
    while True:
        try:
            with connect(autocommit=True) as conn:
                n = jobs.requeue_stale(conn, kind)
                if n:
                    log.warning("put back %d stale %s job(s)", n, kind)
                log.info("worker ready: taking '%s' jobs", kind)
                while True:
                    if not run_one(conn, kind, handler, log):
                        time.sleep(config.JOB_POLL_S)
        except psycopg.OperationalError as e:
            log.warning("lost the db (%s); reconnecting in 2 s", e)
            time.sleep(2)


def run_placeholder(name: str, real_task: str) -> None:
    log = setup(name)
    log.info("placeholder running (real work arrives in %s)", real_task)
    with connect(autocommit=True) as conn:  # no idle open transaction
        last = 0.0
        while True:
            if time.monotonic() - last >= config.WORKER_IDLE_LOG_S:
                log.info("alive; db reachable=%s", ping(conn))
                last = time.monotonic()
            time.sleep(5)
