"""Database access (PostgreSQL via psycopg 3). Every service uses these helpers."""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Optional

import psycopg
from psycopg.rows import dict_row

from server import config

log = logging.getLogger(__name__)

EVENTS_CHANNEL = "sp_events"   # NOTIFY channel: workers → api → SSE feed (B-T03)


def connect(url: Optional[str] = None, autocommit: bool = False, retries: int = 30) -> psycopg.Connection:
    """Open a connection (rows as dicts). Retries for ~30 s so services survive the db starting slowly."""
    url = url or config.DATABASE_URL
    for attempt in range(1, retries + 1):
        try:
            return psycopg.connect(url, autocommit=autocommit, row_factory=dict_row, connect_timeout=5)
        except psycopg.OperationalError:
            if attempt == retries:
                raise
            log.warning("db not reachable (attempt %d/%d), retrying in 1 s", attempt, retries)
            time.sleep(1)
    raise RuntimeError("unreachable")


def ping(conn: psycopg.Connection) -> bool:
    try:
        conn.execute("SELECT 1")
        return True
    except psycopg.Error:
        return False


def notify(conn: psycopg.Connection, event: str, data: dict[str, Any]) -> None:
    """Publish a live-feed event (delivered when the transaction commits)."""
    payload = json.dumps({"event": event, "data": data}, separators=(",", ":"), default=str)
    conn.execute("SELECT pg_notify(%s, %s)", (EVENTS_CHANNEL, payload))
    from server import activity   # D-024: the same event, kept for the admins' activity log
    activity.from_event(conn, event, data)
