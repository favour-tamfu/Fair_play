"""B-T14: calibration → catch rate (contract §4, ±60 s), clock_skew and meter_moved flags."""
from datetime import datetime, timedelta, timezone

import pytest

from fairplay_core.schema import format_utc
from fairplay_core.signing import generate_seed, sign_batch
from server.calibration import recheck_recent
from server.db import connect
from server.tests.test_ingest import SEED, T0, clean, client, hb, make, q  # noqa: F401  (fixtures: M-90 registered)

NOW = datetime.now(timezone.utc).replace(microsecond=0)
SONGS = ["S-000001", "S-000002", "S-000003", "S-000004"]


def cal(run_id="CAL-1", seed=SEED, meter="M-90", expected=None):
    expected = expected if expected is not None else \
        [{"song_id": s, "played_at": format_utc(NOW - timedelta(minutes=20 - 4 * i))} for i, s in enumerate(SONGS)]
    return sign_batch(seed, {"meter_id": meter, "run_id": run_id, "started_at": format_utc(NOW - timedelta(minutes=21)),
                             "ended_at": format_utc(NOW - timedelta(minutes=3)), "expected": expected})


def matched(db, song, played_at_min, offset_s=40.0, accepted=True, shift_s=0):
    """An accepted match of `song` whose back-computed start = played time + shift_s."""
    start = NOW - timedelta(minutes=played_at_min) + timedelta(seconds=shift_s)
    with connect(db, autocommit=True) as c:
        c.execute("""INSERT INTO match_events (meter_id, venue_id, window_start, song_id, offset_s, accepted)
                     VALUES ('M-90', 'V-BUEA-CIMFEST', %s, %s, %s, %s)""",
                  (start + timedelta(seconds=offset_s), song, offset_s, accepted))


@pytest.fixture(autouse=True)
def fresh(migrated_db):
    with connect(migrated_db, autocommit=True) as c:
        c.execute("TRUNCATE calibrations, flags")
        c.execute("UPDATE meters SET catch_rate = 0.8, cell_id = NULL WHERE meter_id = 'M-90'")


def test_calibration_catch_rate_within_60_s(client, migrated_db):
    matched(migrated_db, "S-000001", 20)                    # caught exactly
    matched(migrated_db, "S-000002", 16, shift_s=55)        # caught at +55 s
    matched(migrated_db, "S-000003", 12, shift_s=75)        # too late: not caught
    matched(migrated_db, "S-000004", 8, accepted=False)     # matched window not accepted: not caught
    r = client.post("/v1/calibration", json=cal())
    assert r.status_code == 200
    b = r.json()
    assert (b["ok"], b["run_id"], b["matched"], b["total"], b["catch_rate"], b["applied"]) == (True, "CAL-1", 2, 4, 0.5, True)
    assert q(migrated_db, "SELECT catch_rate FROM meters WHERE meter_id = 'M-90'")[0]["catch_rate"] == 0.5
    det = q(migrated_db, "SELECT detail FROM calibrations WHERE run_id = 'CAL-1'")[0]["detail"]
    assert [d["caught"] for d in det] == [True, True, False, False]


def test_late_matches_are_picked_up_by_the_recheck(client, migrated_db):
    b = client.post("/v1/calibration", json=cal("CAL-2")).json()
    assert (b["matched"], b["applied"]) == (0, False)                     # nothing matched yet: meter unchanged
    assert q(migrated_db, "SELECT catch_rate FROM meters WHERE meter_id = 'M-90'")[0]["catch_rate"] == 0.8
    for i, s in enumerate(SONGS[:3]):
        matched(migrated_db, s, 20 - 4 * i)
    with connect(migrated_db, autocommit=True) as c:
        out = recheck_recent(c)
    assert [(o["run_id"], o["matched"]) for o in out] == [("CAL-2", 3)]
    assert q(migrated_db, "SELECT catch_rate FROM meters WHERE meter_id = 'M-90'")[0]["catch_rate"] == 0.75
    b = client.post("/v1/calibration", json=cal("CAL-2")).json()            # re-post same run: same answer
    assert (b["matched"], b["total"]) == (3, 4)


def test_calibration_rejects(client):
    assert client.post("/v1/calibration", json=cal(seed=generate_seed())).status_code == 401
    assert client.post("/v1/calibration", json=cal(meter="M-57")).status_code == 404
    assert client.post("/v1/calibration", json=cal(expected=[])).status_code == 422
    bad = cal()
    bad["expected"][0]["song_id"] = "nope"
    assert client.post("/v1/calibration", json=bad).status_code == 422


def test_clock_skew_flag_once_per_hour(client, migrated_db):
    assert client.post("/v1/heartbeat", json=hb(datetime.now(timezone.utc) - timedelta(seconds=2))).status_code == 200
    assert q(migrated_db, "SELECT count(*) AS n FROM flags")[0]["n"] == 0                 # 2 s: fine
    for _ in range(2):
        assert client.post("/v1/heartbeat", json=hb(datetime.now(timezone.utc) - timedelta(seconds=30))).status_code == 200
    f = q(migrated_db, "SELECT type, meter_id, venue_id, detail FROM flags")
    assert len(f) == 1 and f[0]["type"] == "clock_skew" and f[0]["meter_id"] == "M-90"
    assert "behind the server (heartbeat)" in f[0]["detail"]
    assert [x["type"] for x in client.get("/api/v1/flags", params={"period": "live"}).json()] == ["clock_skew"]


def test_batch_from_the_future_flags_clock_ahead(client, migrated_db):
    future = (datetime.now(timezone.utc) + timedelta(minutes=2) - datetime(2026, 11, 24, 21, 0, tzinfo=timezone.utc))
    assert client.post("/v1/batches", json=make(1, seconds=future.total_seconds())).json()["status"] == "stored"
    f = q(migrated_db, "SELECT type, detail FROM flags")
    assert len(f) == 1 and f[0]["type"] == "clock_skew" and "ahead of the server" in f[0]["detail"]


def test_meter_moved_flag(client, migrated_db):
    assert client.post("/v1/batches", json=make(1)).json()["status"] == "stored"          # registers cell 624-01-0412-01733
    assert client.post("/v1/batches", json=make(2, seconds=10)).json()["status"] == "stored"
    assert q(migrated_db, "SELECT count(*) AS n FROM flags WHERE type = 'meter_moved'")[0]["n"] == 0
    for seq in (3, 4):                                                                      # new tower, twice
        assert client.post("/v1/batches", json=make(seq, seconds=10 * seq, cell_id="624-01-0999-00001")).status_code == 200
    f = q(migrated_db, "SELECT detail FROM flags WHERE type = 'meter_moved'")
    assert [x["detail"] for x in f] == ["cell 624-01-0412-01733 -> 624-01-0999-00001 (registered at V-BUEA-CIMFEST)"]


def test_window_lag_flag_for_a_live_meter(client, migrated_db):
    """R-020: queue empty, heartbeat clock right, but the newest window is hours old → clock_skew flag (once)."""
    with connect(migrated_db, autocommit=True) as c:
        c.execute("DELETE FROM raw_batches WHERE meter_id = 'M-90'")
        c.execute("UPDATE meters SET source = 'live' WHERE meter_id = 'M-90'")
    try:
        old = datetime.now(timezone.utc) - timedelta(hours=3, minutes=54)
        assert client.post("/v1/batches", json=make(1, seconds=(old - T0).total_seconds())).status_code == 200
        now = datetime.now(timezone.utc)
        assert client.post("/v1/heartbeat", json=hb(now, queued=5)).status_code == 200   # backlog: no flag
        assert q(migrated_db, "SELECT * FROM flags") == []
        for _ in range(2):
            assert client.post("/v1/heartbeat", json=hb(now, queued=0)).status_code == 200
        f = q(migrated_db, "SELECT type, meter_id, detail FROM flags")
        assert len(f) == 1 and f[0]["type"] == "clock_skew" and "3 h 54 min ago" in f[0]["detail"]
        with connect(migrated_db, autocommit=True) as c:                                  # a fresh window: no flag
            c.execute("TRUNCATE flags")
        assert client.post("/v1/batches", json=make(2, seconds=(now - timedelta(seconds=15) - T0).total_seconds())).status_code == 200
        assert client.post("/v1/heartbeat", json=hb(now, queued=0)).status_code == 200
        assert q(migrated_db, "SELECT * FROM flags") == []
    finally:
        with connect(migrated_db, autocommit=True) as c:
            c.execute("UPDATE meters SET source = 'virtual' WHERE meter_id = 'M-90'")
            c.execute("DELETE FROM match_events WHERE meter_id = 'M-90'")
            c.execute("DELETE FROM raw_batches WHERE meter_id = 'M-90'")
