"""The job board: a Postgres table as a work queue (PLAN_B B-T02). No Redis/Kafka needed.

enqueue() pins a ticket; claim() lets exactly one worker take the oldest queued ticket of a kind
(FOR UPDATE SKIP LOCKED: two workers never get the same job); done()/fail() close it.
"""
from __future__ import annotations

from typing import Any, Optional

import psycopg

CLAIM_SQL = """
UPDATE jobs SET status = 'running', attempts = attempts + 1, updated_at = now()
WHERE id = (SELECT id FROM jobs WHERE kind = %s AND status = 'queued' ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1)
RETURNING *
"""


def enqueue(conn: psycopg.Connection, kind: str, ref: str) -> int:
    return conn.execute("INSERT INTO jobs (kind, ref) VALUES (%s, %s) RETURNING id", (kind, str(ref))).fetchone()["id"]


def claim(conn: psycopg.Connection, kind: str) -> Optional[dict[str, Any]]:
    return conn.execute(CLAIM_SQL, (kind,)).fetchone()


def done(conn: psycopg.Connection, job_id: int) -> None:
    conn.execute("UPDATE jobs SET status = 'done', error = NULL, updated_at = now() WHERE id = %s", (job_id,))


def fail(conn: psycopg.Connection, job_id: int, error: str) -> None:
    conn.execute("UPDATE jobs SET status = 'error', error = %s, updated_at = now() WHERE id = %s",
                 (error[:2000], job_id))


def requeue_stale(conn: psycopg.Connection, kind: str, older_than_s: int = 120) -> int:
    """Put back jobs left 'running' by a worker that crashed (used at worker start-up)."""
    cur = conn.execute("UPDATE jobs SET status = 'queued', updated_at = now() WHERE kind = %s AND status = 'running' "
                       "AND updated_at < now() - make_interval(secs => %s)", (kind, older_than_s))
    return cur.rowcount
