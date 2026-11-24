"""B-T13: demo reset (D-017) and the per-chain ledger audit (tamper shows within the 2 s ledger check)."""
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from server import config
from server.db import connect
from server.ledger import anchor, audit, chain
from server.stats.run import run_both
from server.tests.test_import_mock import db, write_month  # noqa: F401  (fixture: live venue/meter/play)
from server.tools.import_mock import import_mock

T = datetime(2026, 11, 24, 20, 0, tzinfo=timezone.utc)


def add_live_play(c, i):
    p = {"play_id": f"P-live{i:08d}", "meter_id": "M-07", "venue_id": "V-BUEA-CIMFEST", "song_id": "S-M0001",
         "started_at": T + timedelta(minutes=5 * i), "duration_s": 30.0, "n_windows": 3}
    prev, h = chain.append(c, p)
    c.execute("""INSERT INTO plays (play_id, meter_id, venue_id, song_id, started_at, duration_s, n_windows, source,
                 prev_chain_hash, chain_hash) VALUES (%s,'M-07','V-BUEA-CIMFEST','S-M0001',%s,30,3,'live',%s,%s)""",
              (p["play_id"], p["started_at"], prev, h))
    return prev


@pytest.fixture
def world(db, tmp_path, monkeypatch):                                          # noqa: F811
    monkeypatch.setattr(config, "ANCHORS_DIR", tmp_path / "anchors")
    audit._cache.clear()
    with connect(db, autocommit=True) as c:
        c.execute("TRUNCATE raw_batches, match_events, jobs, playlogger_state, ledger_epochs, anchors_archive")
        import_mock(c, write_month(tmp_path / "mm"))
        for i in range(2, 5):
            add_live_play(c, i)
        c.execute("INSERT INTO raw_batches (meter_id, venue_id, seq, window_start, body) VALUES "
                  "('M-07','V-BUEA-CIMFEST',5,%s,'{}')", (T,))
        c.execute("INSERT INTO match_events (meter_id, venue_id, window_start, song_id, accepted) VALUES "
                  "('M-07','V-BUEA-CIMFEST',%s,'S-M0001',true)", (T,))
        c.execute("INSERT INTO windows (meter_id, window_start, loudness_db, received, source) VALUES ('M-07',%s,-20,true,'live')", (T,))
        c.execute("INSERT INTO jobs (kind, ref, status) VALUES ('match','1','done'), ('fingerprint','S-000001','done')")
        run_both(c, "live")
        run_both(c, "mock_month")
        hour = c.execute("SELECT date_trunc('hour', min(inserted_at)) AS h FROM plays WHERE chain = 'live'").fetchone()["h"]
        assert anchor.anchor_hour(c, hour) is not None
    return db


def test_reset_wipes_live_keeps_catalogue_and_mock(world):
    from server.demo import reset_live
    with connect(world, autocommit=True) as c:
        mock_before = c.execute("SELECT count(*) AS n, max(chain_hash) AS h FROM plays WHERE chain = 'mock'").fetchone()
        r = reset_live(c, "test reset")
        assert (r["epoch"], r["plays_removed"], r["batches_removed"], r["match_events_removed"], r["windows_removed"],
                r["jobs_removed"], r["anchors_archived"]) == (1, 4, 1, 1, 1, 1, 1)
        n = lambda sql: c.execute(sql).fetchone()["n"]                          # noqa: E731
        assert n("SELECT count(*) AS n FROM plays WHERE chain = 'live'") == 0
        assert c.execute("SELECT count(*) AS n, max(chain_hash) AS h FROM plays WHERE chain = 'mock'").fetchone() == mock_before
        assert n("SELECT count(*) AS n FROM stats_runs WHERE period = 'live'") == 0
        assert n("SELECT count(*) AS n FROM stats_runs WHERE period = 'mock_month'") == 2
        assert n("SELECT count(*) AS n FROM songs") == 3 and n("SELECT count(*) AS n FROM jobs WHERE kind = 'fingerprint'") == 1
        assert c.execute("SELECT public_key_b64 FROM meters WHERE meter_id = 'M-07'").fetchone()["public_key_b64"] == "KEY"
        assert n("SELECT count(*) AS n FROM anchors") == 0 and n("SELECT count(*) AS n FROM anchors_archive WHERE epoch = 0") == 1
        assert audit.status(c)["intact"]
        assert add_live_play(c, 9) == chain.GENESIS                             # new live chain starts from genesis
        assert audit.status(c)["intact"]
    last = json.loads((config.ANCHORS_DIR / "anchors.jsonl").read_text().splitlines()[-1])
    assert (last["event"], last["epoch"], last["plays_removed"]) == ("epoch", 1, 4)


def test_tamper_rewalks_only_the_changed_chain(world):
    with connect(world, autocommit=True) as c:
        assert audit.status(c)["intact"]
        mock_entry = audit._cache[("chain", "mock")]
        c.execute("UPDATE plays SET song_id = 'S-M0003' WHERE play_id = 'P-live00000003'")
        s = audit.status(c)
        assert not s["intact"] and s["broken_at_play_id"] == "P-live00000003"
        assert audit._cache[("chain", "mock")] is mock_entry                     # 65 000-play chain not re-walked
        c.execute("UPDATE plays SET song_id = 'S-M0001' WHERE play_id = 'P-live00000003'")
        assert audit.status(c)["intact"]
        assert audit.full_audit(c)["plays_checked"] == 8                          # 4 live + 4 mock


def test_reset_endpoint_needs_confirm(world):
    from server.api.main import app
    with TestClient(app) as cl:
        assert cl.post("/api/v1/demo/reset").status_code == 422
        assert cl.post("/api/v1/demo/reset", params={"confirm": "no"}).status_code == 422
        r = cl.post("/api/v1/demo/reset", params={"confirm": "yes"}).json()
        assert r["ok"] and r["plays_removed"] == 4 and r["stats_run_id"].startswith("R-")
        assert cl.get("/api/v1/ledger/status").json()["intact"]
        assert cl.get("/api/v1/plays", params={"period": "live"}).json() == []
        assert len(cl.get("/api/v1/plays", params={"period": "mock_month"}).json()) == 4
