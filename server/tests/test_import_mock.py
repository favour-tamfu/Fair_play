"""B-T11: mock month importer (contract §7, D-013) + compare-flat (brief §7.4), on a 2-venue mini month."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from server import config
from server.db import connect
from server.ledger import audit, chain
from server.stats import compare
from server.stats.run import load_meters
from server.tools.import_mock import MockDataError, import_mock

T0 = datetime(2026, 10, 24, 18, 0, tzinfo=timezone.utc)
POT = 1_000_000


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def write_month(folder: Path, drop_live_venue=False, bad_song=False) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    venues = [("V-BUEA-CIMFEST", "CIMFEST demo table", "Buea", 4.1527, 9.2410, "S", "BUEA-S", 40, 18, 2),
              ("V-DLA-AKWA01", "Mock bar Douala 01", "Douala", 4.0474, 9.7894, "M", "DLA-M", 2975, 18, 2)]
    if drop_live_venue:
        venues = venues[1:]
    pd.DataFrame(venues, columns=["venue_id", "name", "city", "lat", "lon", "size_class", "stratum", "bars_in_stratum",
                                  "open_hour", "close_hour"]).to_csv(folder / "venues.csv", index=False)
    # M-07 clashes with the live meter (other venue, other catch rate); M-41 is mock only
    pd.DataFrame([("M-07", "V-DLA-AKWA01", 0.5, "2026-10-12T00:00:00.000Z"),
                  ("M-41", "V-BUEA-CIMFEST", 1.0, "2026-10-12T00:00:00.000Z")],
                 columns=["meter_id", "venue_id", "catch_rate_true", "installed_at"]).to_csv(folder / "meters.csv", index=False)
    pd.DataFrame([("S-M0001", "Mock Song 001", "Mock Artist 01", "CM-SPF-26-00001", 200, 1),
                  ("S-M0002", "Mock Song 002", "Mock Artist 01", "CM-SPF-26-00002", 200, 2),
                  ("S-M0003", "Mock Song 003", "Mock Artist 02", "CM-SPF-26-00003", 200, 3)],
                 columns=["song_id", "title", "artist_name", "isrc", "duration_s", "popularity_rank"]
                 ).to_csv(folder / "songs_synthetic.csv", index=False)
    pd.DataFrame([(s, f"Mock Singer {s[-1]}", "singer", 100.0, "+237699000001") for s in ("S-M0001", "S-M0002", "S-M0003")],
                 columns=["song_id", "owner_name", "role", "share_pct", "momo"]).to_csv(folder / "owners_synthetic.csv", index=False)
    truth = ["S-M0001"] * 6 + ["S-M0002"] * 2 + ["S-M0003"] * 2          # artist 01: 0.8, artist 02: 0.2
    pd.DataFrame([(f"TP-{i:07d}", "V-DLA-AKWA01", s, iso(T0 + timedelta(minutes=10 * i)), 200, "normal")
                  for i, s in enumerate(truth)],
                 columns=["true_play_id", "venue_id", "song_id", "started_at", "duration_s", "scenario"]
                 ).to_csv(folder / "plays_true.csv", index=False)
    obs = [("P-0000002", "V-DLA-AKWA01", "M-07", "S-M0001", 10), ("P-0000001", "V-DLA-AKWA01", "M-07", "S-M0002", 0),
           ("P-0000003", "V-BUEA-CIMFEST", "M-41", "S-M0003", 20), ("P-0000004", "V-BUEA-CIMFEST", "M-41", "S-M0001", 30)]
    if bad_song:
        obs.append(("P-0000005", "V-DLA-AKWA01", "M-07", "S-M9999", 40))
    pd.DataFrame([(p, v, m, s, iso(T0 + timedelta(minutes=k)), 200, -22.5, "mock", "normal") for p, v, m, s, k in obs],
                 columns=["play_id", "venue_id", "meter_id", "song_id", "started_at", "duration_s", "loudness_db", "source",
                          "scenario"]).to_csv(folder / "plays_observed.csv", index=False)
    pd.DataFrame([(m, iso(T0 + timedelta(minutes=10 * k)), 10, 60, 60, -21.0) for m in ("M-07", "M-41") for k in range(3)],
                 columns=["meter_id", "slot_start", "slot_minutes", "windows_received", "windows_expected",
                          "mean_loudness_db"]).to_csv(folder / "windows_observed.csv", index=False)
    return folder


@pytest.fixture
def db(migrated_db, monkeypatch):
    """Live world first: venue, live meter M-07 (key, catch 0.8) and one live play on the live chain."""
    monkeypatch.setattr(config, "DATABASE_URL", migrated_db)
    with connect(migrated_db, autocommit=True) as c, c.transaction():
        c.execute("TRUNCATE plays, play_extents, play_corrections, play_weights, stats_runs, shares, flags, windows, "
                  "songs, owners, meters, venues, mock_meters, window_slots, mock_truth, anchors CASCADE")
        c.execute("INSERT INTO venues (venue_id, name, source) VALUES ('V-BUEA-CIMFEST', 'live table', 'live')")
        c.execute("INSERT INTO meters (meter_id, venue_id, public_key_b64, source, catch_rate) "
                  "VALUES ('M-07', 'V-BUEA-CIMFEST', 'KEY', 'live', 0.8)")
        p = {"play_id": "P-live00000001", "meter_id": "M-07", "venue_id": "V-BUEA-CIMFEST", "song_id": "S-000001",
             "started_at": datetime(2026, 11, 24, 20, 0, tzinfo=timezone.utc), "duration_s": 30.0, "n_windows": 3}
        prev, h = chain.append(c, p)
        c.execute("""INSERT INTO plays (play_id, meter_id, venue_id, song_id, started_at, duration_s, n_windows, source,
                     prev_chain_hash, chain_hash) VALUES (%s,'M-07','V-BUEA-CIMFEST','S-000001',%s,30,3,'live',%s,%s)""",
                  (p["play_id"], p["started_at"], prev, h))
    return migrated_db


def test_import_keeps_live_world_and_is_idempotent(db, tmp_path):
    folder = write_month(tmp_path / "mm")
    with connect(db, autocommit=True) as c:
        a = import_mock(c, folder)
        b = import_mock(c, folder)                                          # re-import: wipe + same result
        assert a["chain_head"] == b["chain_head"] and a["meters_kept_live"] == ["M-07"]
        n = {r["chain"]: r["n"] for r in c.execute("SELECT chain, count(*) AS n FROM plays GROUP BY 1")}
        assert n == {"live": 1, "mock": 4}
        live = c.execute("SELECT * FROM meters WHERE meter_id = 'M-07'").fetchone()
        assert (live["venue_id"], live["public_key_b64"], live["source"], live["catch_rate"]) == \
            ("V-BUEA-CIMFEST", "KEY", "live", 0.8)                          # live meter untouched
        assert c.execute("SELECT source FROM meters WHERE meter_id = 'M-41'").fetchone()["source"] == "mock"
        v = c.execute("SELECT source, stratum FROM venues WHERE venue_id = 'V-BUEA-CIMFEST'").fetchone()
        assert (v["source"], v["stratum"]) == ("live", "BUEA-S")            # live venue keeps source, gets fields
        assert c.execute("SELECT count(*) AS n FROM songs WHERE source = 'mock' AND status = 'ready'").fetchone()["n"] == 3
        assert c.execute("SELECT count(*) AS n FROM owners").fetchone()["n"] == 3
        assert c.execute("SELECT count(*) AS n FROM window_slots").fetchone()["n"] == 6
        assert c.execute("SELECT count(*) AS n FROM mock_truth").fetchone()["n"] == 10
        # mock chain: own genesis, time order (P-0000001 at T0 comes first although it is 2nd in the file)
        first = c.execute("SELECT play_id, prev_chain_hash FROM plays WHERE chain = 'mock' ORDER BY seq_no LIMIT 1").fetchone()
        assert (first["play_id"], first["prev_chain_hash"]) == ("P-0000001", chain.GENESIS)
        # catch rate of the mock month comes from mock_meters even for the clashing id
        assert dict(load_meters(c, ["M-07"], "mock_month").values) == {"M-07": 0.5}
        assert dict(load_meters(c, ["M-07"], "live").values) == {"M-07": 0.8}


def test_ledger_audits_both_chains(db, tmp_path):
    with connect(db, autocommit=True) as c:
        import_mock(c, write_month(tmp_path / "mm"))
        r = audit.full_audit(c)
        assert r["intact"] and r["plays_checked"] == 5
        c.execute("UPDATE plays SET song_id = 'S-M0003' WHERE play_id = 'P-0000004'")      # tamper a mock play
        r = audit.full_audit(c)
        assert not r["intact"] and r["broken_at_play_id"] == "P-0000004"


def test_compare_flat_against_truth(db, tmp_path):
    from server.api.main import app
    from server.stats.run import run_both
    with connect(db, autocommit=True) as c:
        assert compare.compare_flat(c, POT)["n_artists"] == 0                # nothing imported yet
        import_mock(c, write_month(tmp_path / "mm"))
        run_both(c, "mock_month")
        r = compare.compare_flat(c, POT)
        assert (r["n_artists"], r["flat_each_fcfa"]) == (2, 500_000)
        assert r["misallocated_flat_fcfa"] == 300_000                         # 0.5 × pot × (|0.5−0.8| + |0.5−0.2|)
        rid = c.execute("SELECT stats_run_id FROM stats_runs WHERE period = 'mock_month' AND mode = 'standardised'"
                        ).fetchone()["stats_run_id"]
        sh = {x["song_id"]: x["share"] for x in c.execute("SELECT song_id, share FROM shares WHERE stats_run_id = %s", (rid,))}
        a1, a2 = sh["S-M0001"] + sh["S-M0002"], sh["S-M0003"]
        assert r["misallocated_fairplay_fcfa"] == round(0.5 * POT * (abs(a1 - 0.8) + abs(a2 - 0.2)))
    schema = json.loads((config.SCHEMAS_DIR / "compare_flat.schema.json").read_text("utf-8"))
    with TestClient(app) as cl:
        body = cl.get("/api/v1/compare-flat", params={"pot": POT}).json()
    assert list(Draft202012Validator(schema).iter_errors(body)) == [] and body["n_artists"] == 2


def test_misallocated_pure():
    t = pd.Series({"a": 0.75, "b": 0.25})
    assert compare.misallocated(100, pd.Series({"a": 0.5, "b": 0.5}), t) == 25
    assert compare.misallocated(100, pd.Series({"a": 1.0}), t) == 25         # missing artist counts as 0
    assert compare.misallocated(100, t, t) == 0


@pytest.mark.parametrize("kw, why", [({"drop_live_venue": True}, "V-BUEA-CIMFEST"), ({"bad_song": True}, "S-M9999")])
def test_bad_month_rejected_nothing_written(db, tmp_path, kw, why):
    with connect(db, autocommit=True) as c:
        with pytest.raises(MockDataError, match=why):
            import_mock(c, write_month(tmp_path / "mm", **kw))
        assert c.execute("SELECT count(*) AS n FROM plays WHERE chain = 'mock'").fetchone()["n"] == 0
