"""B-T08: read API — every response validates against contract/schemas, empty and populated; filters; static web."""
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from server import config
from server.db import connect
from server.ledger import chain

NOW = datetime.now(timezone.utc).replace(microsecond=0)
SCHEMA = {}


def valid(name, body):
    if name not in SCHEMA:
        SCHEMA[name] = Draft202012Validator(json.loads((config.SCHEMAS_DIR / f"{name}.schema.json").read_text("utf-8")))
    errors = [f"{list(e.path)}: {e.message}" for e in SCHEMA[name].iter_errors(body)]
    assert errors == [], errors
    return body


@pytest.fixture(scope="module")
def client(migrated_db):
    mp = pytest.MonkeyPatch()
    mp.setattr(config, "DATABASE_URL", migrated_db)
    from server.api.main import app
    with TestClient(app) as c:
        yield c
    mp.undo()


def wipe(db):
    with connect(db, autocommit=True) as c:
        c.execute("TRUNCATE plays, play_extents, play_corrections, play_weights, stats_runs, shares, flags, anchors, "
                  "unidentified, songs, owners, fp_hashes, match_events, raw_batches, windows, jobs, meters, venues CASCADE")


def insert_play(c, pid, song, meter, venue, started, source, dur=200.0):
    p = {"play_id": pid, "meter_id": meter, "venue_id": venue, "song_id": song, "started_at": started,
         "duration_s": 30.0, "n_windows": 3}
    prev, h = chain.append(c, p)
    c.execute("""INSERT INTO plays (play_id, meter_id, venue_id, song_id, started_at, duration_s, n_windows, source,
                 prev_chain_hash, chain_hash) VALUES (%s,%s,%s,%s,%s,30.0,3,%s,%s,%s)""",
              (pid, meter, venue, song, started, source, prev, h))
    c.execute("INSERT INTO play_extents (play_id, ended_at, n_windows, duration_s, venue_day) VALUES (%s,%s,20,%s,%s)",
              (pid, started + timedelta(seconds=dur), dur, started.date()))


@pytest.fixture
def world(migrated_db, client):
    """Live venue (filled from KNOWN_VENUES at start-up), a mock venue, 3 songs, live + mock plays, one stats run."""
    wipe(migrated_db)
    with connect(migrated_db, autocommit=True) as c, c.transaction():
        from server.registry import fill_known_venues
        fill_known_venues(c)
        c.execute("""INSERT INTO venues (venue_id, name, city, lat, lon, stratum, bars_in_stratum, source)
                     VALUES ('V-DLA-AKWA01','Mock Bar Akwa 1','Douala',4.05,9.77,'DOUA-L',1275,'mock')""")
        c.execute("""INSERT INTO meters (meter_id, venue_id, public_key_b64, last_seen, source) VALUES
                     ('M-07','V-BUEA-CIMFEST','k', now(), 'live'), ('M-11','V-DLA-AKWA01','k', NULL, 'mock')""")
        for sid, t, a, st in (("S-000001", "Makossa Night", "Ada", "ready"), ("S-000002", "Bikutsi Morning", "Ben", "ready"),
                              ("S-M0001", "Mock Song 001", "Mock Artist 01", "ready")):
            c.execute("INSERT INTO songs (song_id, title, artist_name, status, source) VALUES (%s,%s,%s,%s,%s)",
                      (sid, t, a, st, "mock" if sid.startswith("S-M") else "upload"))
        for i in range(4):
            insert_play(c, f"P-live{i:08d}", "S-000001" if i < 3 else "S-000002", "M-07", "V-BUEA-CIMFEST",
                        NOW - timedelta(minutes=10 * (4 - i)), "live")
        insert_play(c, "P-mock00000001", "S-M0001", "M-11", "V-DLA-AKWA01", NOW - timedelta(days=5), "mock")
        insert_play(c, "P-gone00000001", "S-000002", "M-07", "V-BUEA-CIMFEST", NOW - timedelta(minutes=1), "live")
        c.execute("INSERT INTO play_corrections (play_id, reason, detail) VALUES ('P-gone00000001','not_confirmed_on_recompute','{}')")
        c.execute("INSERT INTO unidentified (meter_id, day, seconds) VALUES ('M-07', %s, 90)", (NOW.date(),))
        c.execute("INSERT INTO flags (type, song_id, venue_id, detail) VALUES ('loop','S-000001','V-BUEA-CIMFEST','3 loops')")
    return migrated_db


def add_stats_run(db):
    with connect(db, autocommit=True) as c, c.transaction():
        c.execute("""INSERT INTO stats_runs (stats_run_id, period, mode, rule_version, started_at, finished_at, params)
                     VALUES ('R-20261124213000','live','standardised','sr-1.0', now(), now(), %s)""",
                  (json.dumps({"pot_fcfa": 100_000_000, "escrow_share": 0.05}),))
        for i, (w, why) in enumerate([(1, "streak_1"), (1, "streak_2"), (0.5, "streak_3"), (1, "streak_1")]):
            c.execute("INSERT INTO play_weights VALUES (%s,'sr-1.0','R-20261124213000',%s,%s)", (f"P-live{i:08d}", w, [why]))
        for sid, raw, wp, sh in (("S-000001", 3, 2.5, 0.7142857), ("S-000002", 1, 1.0, 0.2857143)):
            c.execute("INSERT INTO shares VALUES ('R-20261124213000',%s,%s,%s,%s,%s,%s,%s)",
                      (sid, raw, wp, sh, sh * 0.8, min(1, sh * 1.2), []))


# ---------------------------------------------------------------- empty database

def test_empty_shapes_are_valid(migrated_db, client):
    wipe(migrated_db)
    valid("overview", client.get("/api/v1/overview").json())
    assert valid("venues", client.get("/api/v1/venues").json()) == []
    assert valid("plays", client.get("/api/v1/plays").json()) == []
    s = valid("shares", client.get("/api/v1/shares").json())
    assert s["stats_run_id"] is None and s["rows"] == []
    valid("flags", client.get("/api/v1/flags").json())
    valid("payouts", client.get("/api/v1/payouts").json())
    assert valid("compare_flat", client.get("/api/v1/compare-flat").json())["n_artists"] == 0
    valid("artists", client.get("/api/v1/artists").json())


# ---------------------------------------------------------------- populated

def test_overview(world, client):
    o = valid("overview", client.get("/api/v1/overview", params={"period": "live"}).json())
    assert o["plays_raw"] == 4 and o["plays_counted"] == 4.0                # superseded play excluded; no stats yet
    assert o["meters_online"] == 1 and o["meters_total"] == 2 and o["venues"] == 2
    assert o["unidentified_music_min"] == 1.5 and o["ledger_intact"] is True
    add_stats_run(world)
    assert client.get("/api/v1/overview", params={"period": "live"}).json()["plays_counted"] == 3.5


def test_venues_live_venue_has_known_coordinates(world, client):
    vs = {v["venue_id"]: v for v in valid("venues", client.get("/api/v1/venues").json())}
    live = vs["V-BUEA-CIMFEST"]
    assert (live["name"], live["city"], live["lat"], live["lon"]) == ("CIMFEST demo table", "Buea", 4.1527, 9.241)
    assert live["meters"][0]["meter_id"] == "M-07" and live["meters"][0]["online"] is True
    assert vs["V-DLA-AKWA01"]["meters"][0]["online"] is False


def test_plays_filters_order_and_weights(world, client):
    live = valid("plays", client.get("/api/v1/plays", params={"period": "live"}).json())
    assert [p["play_id"] for p in live] == ["P-live00000003", "P-live00000002", "P-live00000001", "P-live00000000"]
    assert all(p["weight"] is None and p["reasons"] == [] for p in live)      # before stats
    assert live[0]["duration_s"] == 200.0 and live[0]["title"] == "Bikutsi Morning"     # duration from extents
    assert [p["play_id"] for p in client.get("/api/v1/plays", params={"period": "mock_month"}).json()] == ["P-mock00000001"]
    assert len(client.get("/api/v1/plays", params={"song_id": "S-000001"}).json()) == 3
    assert len(client.get("/api/v1/plays", params={"venue_id": "V-DLA-AKWA01"}).json()) == 1
    assert len(client.get("/api/v1/plays", params={"limit": 2}).json()) == 2
    add_stats_run(world)
    w = {p["play_id"]: (p["weight"], p["reasons"]) for p in client.get("/api/v1/plays", params={"period": "live"}).json()}
    assert w["P-live00000002"] == (0.5, ["streak_3"])
    raw = client.get("/api/v1/plays", params={"period": "live", "mode": "raw"}).json()
    assert all(p["weight"] is None for p in raw)                              # no raw run stored in this test


def test_shares_amounts_sum_to_pot(world, client):
    add_stats_run(world)
    s = valid("shares", client.get("/api/v1/shares", params={"period": "live"}).json())
    assert s["stats_run_id"] == "R-20261124213000" and s["escrow_share"] == 0.05
    assert [r["song_id"] for r in s["rows"]] == ["S-000001", "S-000002"]
    assert sum(r["amount_fcfa"] for r in s["rows"]) == 100_000_000


def test_flags_payouts_frozen_and_artists(world, client):
    assert valid("flags", client.get("/api/v1/flags").json())[0]["type"] == "loop"
    assert valid("payouts", client.get("/api/v1/payouts").json())["frozen"] is False
    with connect(world, autocommit=True) as c:
        c.execute("UPDATE plays SET song_id = 'S-000002' WHERE play_id = 'P-live00000000'")      # tamper
    assert client.get("/api/v1/payouts").json()["frozen"] is True
    names = [a["artist_name"] for a in valid("artists", client.get("/api/v1/artists").json())]
    assert names == ["Ada", "Ben", "Mock Artist 01"]


def test_artist_page(world, client):
    add_stats_run(world)
    a = valid("artist", client.get("/api/v1/artists/Ada", params={"period": "live"}).json())
    assert a["songs"] == [{"song_id": "S-000001", "title": "Makossa Night"}]
    assert a["plays_by_venue"] == [{"venue_id": "V-BUEA-CIMFEST", "name": "CIMFEST demo table", "city": "Buea",
                                    "plays_raw": 3, "plays_counted": 2.5}]
    assert sum(d["plays_raw"] for d in a["plays_by_day"]) == 3 and len(a["recent"]) == 3
    assert a["amount_fcfa"] == client.get("/api/v1/shares", params={"period": "live"}).json()["rows"][0]["amount_fcfa"]
    assert client.get("/api/v1/artists/Nobody").status_code == 404


def test_bad_query_params_rejected(client):
    assert client.get("/api/v1/plays", params={"period": "yesterday"}).status_code == 422
    assert client.get("/api/v1/shares", params={"mode": "fancy"}).status_code == 422


def test_static_web_is_mounted_after_api(client):
    files = [p for p in config.WEB_DIR.iterdir() if p.is_file()]      # whatever A has put in web/ (contract §6.2)
    if files:
        assert client.get("/" + files[0].name).status_code == 200      # served at the root
    if (config.WEB_DIR / "index.html").exists():
        assert client.get("/").status_code == 200
    assert client.get("/health").json()["ok"] is True                  # API routes are not shadowed
    assert client.get("/api/v1/venues").status_code == 200
