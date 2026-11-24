"""B-T07: hash chain auditor, Merkle roots, anchors, scheduler alerts, tamper tool, ledger endpoints."""
import hashlib
import json
from datetime import datetime, timedelta, timezone

import psycopg
import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from server import config
from server.db import EVENTS_CHANNEL, connect
from server.ledger import anchor, audit, chain
from server.ledger.merkle import merkle_root
from server.tools import tamper
from server.workers.scheduler import Scheduler

T0 = datetime(2026, 11, 24, 20, 0, tzinfo=timezone.utc)


def add_plays(db, n, song="S-000001", start=0):
    with connect(db, autocommit=True) as c, c.transaction():
        for i in range(start, start + n):
            p = {"play_id": f"P-{i:012x}", "meter_id": "M-90", "venue_id": "V-BUEA-CIMFEST", "song_id": song,
                 "started_at": T0 + timedelta(minutes=4 * i), "duration_s": 200.0, "n_windows": 20}
            prev, h = chain.append(c, p)
            c.execute("""INSERT INTO plays (play_id, meter_id, venue_id, song_id, started_at, duration_s, n_windows, source,
                         prev_chain_hash, chain_hash) VALUES (%s,%s,%s,%s,%s,%s,%s,'live',%s,%s)""",
                      (p["play_id"], p["meter_id"], p["venue_id"], song, p["started_at"], 200.0, 20, prev, h))


@pytest.fixture(autouse=True)
def clean(migrated_db, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATABASE_URL", migrated_db)
    monkeypatch.setattr(config, "ANCHORS_DIR", tmp_path / "anchors")
    monkeypatch.setattr(tamper, "BACKUP", tmp_path / "anchors" / "tamper_backup.json")
    with connect(migrated_db, autocommit=True) as c:
        c.execute("TRUNCATE plays, play_extents, play_corrections, anchors, songs CASCADE")
        for sid in ("S-000001", "S-000002"):
            c.execute("INSERT INTO songs (song_id, title, artist_name, status) VALUES (%s, %s, 'T', 'ready')", (sid, sid))


def status(db):
    with connect(db) as c:
        return audit.status(c)


# ---------------------------------------------------------------- merkle

def test_merkle_root_deterministic_and_order_independent():
    hs = [hashlib.sha256(bytes([i])).hexdigest() for i in range(5)]
    assert merkle_root(hs) == merkle_root(list(reversed(hs)))
    assert merkle_root([]) is None and merkle_root(hs[:1]) == hs[0]
    a, b = sorted(bytes.fromhex(h) for h in hs[:2])
    assert merkle_root(hs[:2]) == hashlib.sha256(a + b).hexdigest()
    assert merkle_root(hs) != merkle_root(hs[:4])


# ---------------------------------------------------------------- auditor + tamper

def test_intact_chain(migrated_db):
    add_plays(migrated_db, 6)
    s = status(migrated_db)
    assert s == {"intact": True, "broken_at_play_id": None, "plays_checked": 6, "last_root": None, "last_anchor": None}


def test_tamper_detected_at_the_right_play_and_restore(migrated_db):
    add_plays(migrated_db, 6)
    assert tamper.tamper("P-000000000003", latest=False) == 0
    s = status(migrated_db)
    assert s["intact"] is False and s["broken_at_play_id"] == "P-000000000003"
    with connect(migrated_db) as c:
        assert c.execute("SELECT song_id FROM plays WHERE play_id='P-000000000003'").fetchone()["song_id"] == "S-000002"
    assert tamper.restore() == 0
    assert status(migrated_db)["intact"] is True


@pytest.mark.parametrize("sql", [
    "UPDATE plays SET started_at = started_at + interval '1 hour' WHERE play_id = 'P-000000000002'",
    "UPDATE plays SET duration_s = 9999 WHERE play_id = 'P-000000000002'",
    "UPDATE plays SET chain_hash = repeat('a', 64) WHERE play_id = 'P-000000000002'",
    "DELETE FROM plays WHERE play_id = 'P-000000000002'",
])
def test_any_edit_or_deletion_breaks_the_chain(migrated_db, sql):
    add_plays(migrated_db, 5)
    with connect(migrated_db, autocommit=True) as c:
        c.execute(sql)
    s = status(migrated_db)
    assert s["intact"] is False
    assert s["broken_at_play_id"] in ("P-000000000002", "P-000000000003")    # deleted row → next one breaks


# ---------------------------------------------------------------- anchors

def test_anchor_hour_file_and_audit(migrated_db):
    add_plays(migrated_db, 4)
    with connect(migrated_db, autocommit=True) as c, c.transaction():
        now = datetime.now(timezone.utc)
        row = anchor.anchor_hour(c, now)
        hashes = [r["chain_hash"] for r in c.execute("SELECT chain_hash FROM plays")]
    assert row["n_plays"] == 4 and row["root"] == merkle_root(hashes) and row["via"] == "file"
    line = json.loads((config.ANCHORS_DIR / "anchors.jsonl").read_text().splitlines()[-1])
    assert line["root"] == row["root"] and line["n_plays"] == 4
    s = status(migrated_db)
    assert s["intact"] is True and s["last_root"] == row["root"] and s["last_anchor"]["via"] == "file"

    add_plays(migrated_db, 2, start=10)                     # more plays later in the same hour: old anchor still valid
    assert status(migrated_db)["intact"] is True
    with connect(migrated_db, autocommit=True) as c:        # forging an anchor root is caught
        c.execute("UPDATE anchors SET root = repeat('b', 64)")
    assert status(migrated_db)["intact"] is False


def test_anchor_closed_hours_skips_current_and_is_idempotent(migrated_db):
    add_plays(migrated_db, 3)
    with connect(migrated_db, autocommit=True) as c:
        c.execute("UPDATE plays SET inserted_at = now() - interval '2 hours'")
        with c.transaction():
            assert len(anchor.anchor_closed_hours(c)) == 1
            assert anchor.anchor_closed_hours(c) == []      # already anchored, nothing new
        assert c.execute("SELECT count(*) AS n FROM anchors").fetchone()["n"] == 1


# ---------------------------------------------------------------- scheduler alert

def test_scheduler_announces_ledger_flips(migrated_db):
    add_plays(migrated_db, 3)
    sch = Scheduler()
    with psycopg.connect(migrated_db, autocommit=True) as listener, connect(migrated_db, autocommit=True) as c:
        listener.execute(f"LISTEN {EVENTS_CHANNEL}")
        sch.check_ledger(c)                                  # first check announces the current state
        sch.check_ledger(c)                                  # unchanged → silent
        tamper.tamper(None, latest=True)
        sch.check_ledger(c)
        tamper.restore()
        sch.check_ledger(c)
        got = [json.loads(n.payload)["data"] for n in listener.notifies(timeout=2, stop_after=3)]
    assert got == [{"intact": True, "broken_at_play_id": None},
                   {"intact": False, "broken_at_play_id": "P-000000000002"},
                   {"intact": True, "broken_at_play_id": None}]


# ---------------------------------------------------------------- endpoints

def test_ledger_endpoints(migrated_db):
    from server.api.main import app
    add_plays(migrated_db, 2)
    schema = json.loads((config.SCHEMAS_DIR / "ledger_status.schema.json").read_text(encoding="utf-8"))
    with TestClient(app) as cl:
        body = cl.get("/api/v1/ledger/status").json()
        assert list(Draft202012Validator(schema).iter_errors(body)) == [] and body["intact"] is True
        r = cl.post("/api/v1/ledger/anchor").json()
        assert r["ok"] is True and r["n_plays"] == 2
        anchors = cl.get("/api/v1/ledger/anchors").json()
        assert len(anchors) == 1 and anchors[0]["root"] == r["root"]
        body = cl.get("/api/v1/ledger/status").json()
        assert body["last_anchor"]["root"] == r["root"]
        assert list(Draft202012Validator(schema).iter_errors(body)) == []
