"""B-T03: device ingest API (contract §4) — every response code, side effects, bulk, heartbeat, concurrency, feed."""
import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import psycopg
import pytest
from fastapi.testclient import TestClient

from fairplay_core.schema import format_utc
from fairplay_core.signing import generate_seed, sign_batch
from server import config
from server.db import EVENTS_CHANNEL, connect
from server.ingest import ingest_batch
from server.tools.make_test_vectors import OUT as TV_DIR, SEED, synthetic_peaks, unsigned_batch

T0 = datetime(2026, 11, 24, 21, 0, tzinfo=timezone.utc)


def tv(name):
    return json.loads((TV_DIR / name).read_text(encoding="utf-8"))


def make(seq, seconds=0, seed=SEED, **over):
    """Signed M-90 batch; window_start = T0 + seconds."""
    return sign_batch(seed, unsigned_batch(synthetic_peaks(), seq=seq, window_start=format_utc(T0 + timedelta(seconds=seconds)),
                                           **over))


@pytest.fixture(scope="module")
def client(migrated_db):
    mp = pytest.MonkeyPatch()
    mp.setattr(config, "DATABASE_URL", migrated_db)
    from server.api.main import app
    with TestClient(app) as c:
        keys = tv("tv_keys.json")
        r = c.post("/v1/meters/register", json={k: keys[k] for k in ("meter_id", "venue_id", "public_key_b64", "created_at")})
        assert r.status_code == 200, r.text
        yield c
    mp.undo()


@pytest.fixture(autouse=True)
def clean(migrated_db):
    with connect(migrated_db, autocommit=True) as c:
        c.execute("TRUNCATE raw_batches, match_events, windows, jobs RESTART IDENTITY CASCADE")
        c.execute("UPDATE meters SET last_seq = 0, last_seen = NULL, queued = 0, cell_id = NULL")


def q(db, sql, *args):
    with connect(db) as c:
        return c.execute(sql, args).fetchall()


# ---------------------------------------------------------------- contract test vectors

def test_contract_vectors(client):
    assert client.post("/v1/batches", json=tv("tv_batch_valid.json")).json() == {"ack": 1, "status": "stored"}
    assert client.post("/v1/batches", json=tv("tv_batch_valid.json")).json() == {"ack": 1, "status": "duplicate"}
    r = client.post("/v1/batches", json=tv("tv_batch_badsig.json"))
    assert (r.status_code, r.json()) == (401, {"error": "bad_signature"})
    r = client.post("/v1/batches", json=tv("tv_batch_badversion.json"))
    assert r.status_code == 422 and r.json()["error"] == "invalid" and "fp_version" in r.json()["detail"]


def test_unknown_meter_404(client):
    b = sign_batch(generate_seed(), unsigned_batch(synthetic_peaks(), meter_id="M-55"))
    assert (client.post("/v1/batches", json=b).status_code, client.post("/v1/batches", json=b).json()) == \
        (404, {"error": "unknown_meter"})


def test_seq_conflict_409(client):
    assert client.post("/v1/batches", json=make(5, 0)).status_code == 200
    r = client.post("/v1/batches", json=make(5, 10))          # same seq, different content
    assert (r.status_code, r.json()) == (409, {"error": "seq_conflict"})


@pytest.mark.parametrize("body, why", [(b"{not json", "not JSON"), (b"[1,2]", "not an object")])
def test_bad_bodies_422(client, body, why):
    r = client.post("/v1/batches", content=body, headers={"content-type": "application/json"})
    assert r.status_code == 422 and r.json()["error"] == "invalid", why


def test_missing_sig_422(client):
    b = make(1)
    del b["sig"]
    r = client.post("/v1/batches", json=b)
    assert r.status_code == 422 and "sig" in r.json()["detail"]


def test_rejected_batches_store_nothing(client, migrated_db):
    client.post("/v1/batches", json=tv("tv_batch_badsig.json"))
    client.post("/v1/batches", json=tv("tv_batch_badversion.json"))
    assert q(migrated_db, "SELECT count(*) AS n FROM raw_batches")[0]["n"] == 0
    assert q(migrated_db, "SELECT count(*) AS n FROM jobs")[0]["n"] == 0


# ---------------------------------------------------------------- side effects

def test_stored_batch_side_effects(client, migrated_db):
    client.post("/v1/batches", json=make(7, 30))
    rb = q(migrated_db, "SELECT id, meter_id, seq, window_start, late, processed, body FROM raw_batches")
    assert len(rb) == 1 and rb[0]["seq"] == 7 and rb[0]["late"] is False and rb[0]["processed"] is False
    assert rb[0]["window_start"] == T0 + timedelta(seconds=30)
    assert rb[0]["body"]["sig"] == make(7, 30)["sig"]                     # raw body kept as received
    w = q(migrated_db, "SELECT loudness_db, received, source FROM windows WHERE meter_id='M-90'")
    assert w == [{"loudness_db": -18.4, "received": True, "source": "virtual"}]   # M-90 ≥ M-11 → virtual
    j = q(migrated_db, "SELECT kind, ref, status FROM jobs")
    assert j == [{"kind": "match", "ref": str(rb[0]["id"]), "status": "queued"}]
    m = q(migrated_db, "SELECT last_seq, last_seen, cell_id FROM meters WHERE meter_id='M-90'")[0]
    assert m["last_seq"] == 7 and m["last_seen"] is not None and m["cell_id"] == "624-01-0412-01733"


def test_late_flag_uses_event_time(client, migrated_db):
    client.post("/v1/batches", json=make(10, 600))       # heard 21:10
    client.post("/v1/batches", json=make(11, 0))         # heard 21:00 but arrives after → late
    client.post("/v1/batches", json=make(12, 610))       # newest again → not late
    rows = q(migrated_db, "SELECT seq, late FROM raw_batches ORDER BY seq")
    assert [(r["seq"], r["late"]) for r in rows] == [(10, False), (11, True), (12, False)]
    assert q(migrated_db, "SELECT last_seq FROM meters WHERE meter_id='M-90'")[0]["last_seq"] == 12


# ---------------------------------------------------------------- bulk

def test_bulk_mixed(client, migrated_db):
    client.post("/v1/batches", json=make(1, 0))
    body = {"batches": [make(1, 0), make(2, 10), tv("tv_batch_badsig.json") | {"seq": 3}, make(4, 30),
                        {"nonsense": True}]}
    res = client.post("/v1/batches/bulk", json=body).json()["results"]
    assert [r["status"] for r in res] == ["duplicate", "stored", "error", "stored", "error"]
    assert res[2]["error"] == "bad_signature" and res[4]["error"] == "invalid"
    assert q(migrated_db, "SELECT count(*) AS n FROM raw_batches")[0]["n"] == 3


def test_bulk_limit(client):
    r = client.post("/v1/batches/bulk", json={"batches": [make(i + 1, i * 10) for i in range(51)]})
    assert r.status_code == 422


# ---------------------------------------------------------------- heartbeat + register

def hb(sent_at, queued=4, seed=SEED, meter="M-90"):
    return sign_batch(seed, {"meter_id": meter, "venue_id": "V-BUEA-CIMFEST", "sent_at": format_utc(sent_at),
                             "queued": queued, "fw": "testvector-1"})


def test_heartbeat(client, migrated_db):
    sent = datetime.now(timezone.utc) - timedelta(seconds=3)       # meter clock 3 s behind
    r = client.post("/v1/heartbeat", json=hb(sent))
    assert r.status_code == 200 and r.json()["ok"] is True and r.json()["server_time"].endswith("Z")
    m = q(migrated_db, "SELECT queued, clock_skew_s, last_seen FROM meters WHERE meter_id='M-90'")[0]
    assert m["queued"] == 4 and 2.5 < m["clock_skew_s"] < 10 and m["last_seen"] is not None
    assert client.post("/v1/heartbeat", json=hb(sent, seed=generate_seed())).status_code == 401
    assert client.post("/v1/heartbeat", json=hb(sent, meter="M-56")).status_code == 404
    assert client.post("/v1/heartbeat", json={"meter_id": "M-90"}).status_code == 422


def test_register_rejects_bad_record(client):
    assert client.post("/v1/meters/register", json={"meter_id": "M-91", "venue_id": "bad", "public_key_b64": "x"}
                       ).status_code == 422


def test_startup_loaded_contract_meter_keys(client, migrated_db):
    files = sorted(p.name.split(".")[0] for p in config.METERS_DIR.glob("*.pub.json"))
    rows = {r["meter_id"] for r in q(migrated_db, "SELECT meter_id FROM meters")}
    assert set(files) <= rows                                       # e.g. A's M-07
    if "M-07" in rows:
        assert q(migrated_db, "SELECT source FROM meters WHERE meter_id='M-07'")[0]["source"] == "live"


# ---------------------------------------------------------------- concurrency

def test_100_concurrent_posts(client, migrated_db):
    """50 different batches, each sent twice at the same time (retries) → 50 stored, 50 duplicate, nothing lost."""
    batches = [make(i + 1, i * 10) for i in range(50)] * 2

    def send(b):
        with connect(migrated_db, autocommit=True) as c:
            return ingest_batch(c, b).body["status"]

    with ThreadPoolExecutor(max_workers=20) as ex:
        statuses = list(ex.map(send, batches))
    assert statuses.count("stored") == 50 and statuses.count("duplicate") == 50
    assert q(migrated_db, "SELECT count(*) AS n FROM raw_batches")[0]["n"] == 50
    assert q(migrated_db, "SELECT count(*) AS n FROM jobs WHERE kind='match'")[0]["n"] == 50


# ---------------------------------------------------------------- live feed

def test_stored_batch_emits_batch_and_meter_events(client, migrated_db):
    with psycopg.connect(migrated_db, autocommit=True) as listener:
        listener.execute(f"LISTEN {EVENTS_CHANNEL}")
        client.post("/v1/batches", json=make(3, 20))
        got = [json.loads(n.payload) for n in listener.notifies(timeout=2, stop_after=2)]
    assert [e["event"] for e in got] == ["batch", "meter"]
    assert got[0]["data"] == {"meter_id": "M-90", "venue_id": "V-BUEA-CIMFEST", "seq": 3,
                              "window_start": "2026-11-24T21:00:20.000Z", "late": False}
    assert got[1]["data"]["online"] is True


def test_event_bus_forwards_notify_to_subscribers(migrated_db):
    from server.api.events import EventBus
    from server.db import notify

    async def scenario():
        bus = EventBus()
        bus.start(asyncio.get_running_loop(), migrated_db)
        await asyncio.get_running_loop().run_in_executor(None, bus.ready.wait, 5)
        sub = bus.subscribe()
        with connect(migrated_db, autocommit=True) as c:
            notify(c, "play", {"play_id": "P-test"})
        ev = await asyncio.wait_for(sub.get(), timeout=5)
        bus.stop()
        return ev

    assert asyncio.run(scenario()) == {"event": "play", "data": {"play_id": "P-test"}}
