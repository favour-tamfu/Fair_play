"""Shared worker start-up. Until a worker's real task exists it runs as a placeholder: connects, waits, logs alive."""
from __future__ import annotations

import logging
import time

from server import config
from server.db import connect, ping
from server.db.migrate import migrate


def setup(name: str) -> logging.Logger:
    logging.basicConfig(level=logging.INFO, format=f"%(asctime)s %(levelname)s {name} %(message)s")
    log = logging.getLogger(name)
    migrate()  # safe if the api is migrating at the same time (advisory lock)
    return log


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
