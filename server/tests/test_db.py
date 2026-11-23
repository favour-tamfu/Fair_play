"""B-T02: migrations, job board, /health."""
import re

import pytest

from server.db import connect, jobs
from server.db.migrate import migrate

TABLES = {"venues", "meters", "songs", "owners", "fp_hashes", "raw_batches", "match_events", "plays",
          "play_corrections", "play_weights", "stats_runs", "shares", "flags", "anchors", "calibrations",
          "payouts", "jobs", "windows", "schema_migrations"}


def test_all_tables_exist(migrated_db):
    with connect(migrated_db) as c:
        names = {r["table_name"] for r in c.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")}
    assert TABLES <= names


def test_migrate_is_idempotent(migrated_db):
    assert migrate(migrated_db) == []                     # second run: nothing to do
    with connect(migrated_db) as c:
        versions = [r["version"] for r in c.execute("SELECT version FROM schema_migrations ORDER BY version")]
    assert versions[0] == "001_init" and len(versions) == len(set(versions))


@pytest.fixture
def board(migrated_db):
    with connect(migrated_db, autocommit=True) as c:
        c.execute("DELETE FROM jobs")
    return migrated_db


def test_job_lifecycle(board):
    with connect(board, autocommit=True) as c:
        jid = jobs.enqueue(c, "match", "17")
        job = jobs.claim(c, "match")
        assert job["id"] == jid and job["ref"] == "17" and job["status"] == "running" and job["attempts"] == 1
        assert jobs.claim(c, "match") is None              # nothing else queued
        assert jobs.claim(c, "fingerprint") is None        # other kinds untouched
        jobs.done(c, jid)
        assert c.execute("SELECT status FROM jobs WHERE id=%s", (jid,)).fetchone()["status"] == "done"


def test_two_workers_never_get_the_same_job(board):
    with connect(board, autocommit=True) as c:
        ids = {jobs.enqueue(c, "match", str(i)) for i in range(2)}
    w1, w2 = connect(board), connect(board)               # two workers, each inside an open transaction
    try:
        a, b = jobs.claim(w1, "match"), jobs.claim(w2, "match")   # w1 still holds its row lock
        assert a and b and a["id"] != b["id"] and {a["id"], b["id"]} == ids
    finally:
        w1.rollback(); w2.rollback(); w1.close(); w2.close()


def test_fail_and_requeue_stale(board):
    with connect(board, autocommit=True) as c:
        jid = jobs.enqueue(c, "fingerprint", "S-000001")
        jobs.fail(c, jobs.claim(c, "fingerprint")["id"], "ffmpeg exploded")
        row = c.execute("SELECT status, error FROM jobs WHERE id=%s", (jid,)).fetchone()
        assert row == {"status": "error", "error": "ffmpeg exploded"}

        jid2 = jobs.enqueue(c, "fingerprint", "S-000002")
        jobs.claim(c, "fingerprint")                       # worker "crashes" while running it
        c.execute("UPDATE jobs SET updated_at = now() - interval '10 minutes' WHERE id=%s", (jid2,))
        assert jobs.requeue_stale(c, "fingerprint") == 1
        assert jobs.claim(c, "fingerprint")["id"] == jid2


def test_health(migrated_db, monkeypatch):
    from fastapi.testclient import TestClient
    from server import config
    monkeypatch.setattr(config, "DATABASE_URL", migrated_db)
    from server.api.main import app
    with TestClient(app) as client:
        body = client.get("/health").json()
    assert body["ok"] is True and body["db"] is True and body["version"] == config.VERSION
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$", body["server_time"])
