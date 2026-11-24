"""Tests for the mock month (A-T10): contract headers, IDs, owner shares, scenarios, determinism."""
import csv
import os
from collections import Counter, defaultdict

import pytest

from tools.mockgen.generate import FILES, generate

OUT = os.path.join("contract", "fixtures", "mock_month")


def _rows(name):
    with open(os.path.join(OUT, name), encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _header(name):
    with open(os.path.join(OUT, name), encoding="utf-8") as fh:
        return next(csv.reader(fh))


def test_headers_match_the_contract():
    assert _header("venues.csv") == FILES["venues"]
    assert _header("meters.csv") == FILES["meters"]
    assert _header("songs_synthetic.csv") == FILES["songs"]
    assert _header("owners_synthetic.csv") == FILES["owners"]
    assert _header("plays_true.csv") == FILES["plays_true"]
    assert _header("plays_observed.csv") == FILES["plays_observed"]
    assert _header("windows_observed.csv") == FILES["windows"]


def test_ids_are_unique():
    venues = _rows("venues.csv")
    assert len({v["venue_id"] for v in venues}) == len(venues)
    meters = _rows("meters.csv")
    assert len({m["meter_id"] for m in meters}) == len(meters)
    songs = _rows("songs_synthetic.csv")
    assert len({s["song_id"] for s in songs}) == len(songs)


def test_every_meter_points_at_a_real_venue():
    venue_ids = {v["venue_id"] for v in _rows("venues.csv")}
    for m in _rows("meters.csv"):
        assert m["venue_id"] in venue_ids


def test_owner_shares_add_to_100_per_song():
    total = defaultdict(float)
    for o in _rows("owners_synthetic.csv"):
        total[o["song_id"]] += float(o["share_pct"])
    assert all(abs(v - 100.0) < 1e-6 for v in total.values())
    assert len(total) == len(_rows("songs_synthetic.csv"))


def test_plays_only_use_known_songs_and_venues():
    songs = {s["song_id"] for s in _rows("songs_synthetic.csv")}
    venues = {v["venue_id"] for v in _rows("venues.csv")}
    for p in _rows("plays_true.csv")[:20000]:
        assert p["song_id"] in songs and p["venue_id"] in venues


def test_named_venues_and_scenarios_exist():
    venues = {v["venue_id"] for v in _rows("venues.csv")}
    assert {"V-DLA-AKWA01", "V-YDE-BASTO1", "V-BUEA-MOLYK1", "V-BUEA-CIMFEST"} <= venues
    scen = Counter(p["scenario"] for p in _rows("plays_true.csv"))
    assert scen["loop"] > 0 and scen["promo"] > 0 and scen["quiet_hours"] > 0


def test_loop_song_is_played_on_a_loop_at_akwa():
    loops = [p for p in _rows("plays_true.csv") if p["scenario"] == "loop"]
    assert loops and all(p["song_id"] == "S-M0150" and p["venue_id"] == "V-DLA-AKWA01" for p in loops)
    per_night = Counter(p["started_at"][:10] for p in loops)
    assert max(per_night.values()) == 12


def test_power_cut_meter_has_no_windows_on_the_two_nights():
    rows = [w for w in _rows("windows_observed.csv") if w["meter_id"] == "M-15"]
    dead = [w for w in rows if w["slot_start"][:10] in ("2026-11-08", "2026-11-09")]
    assert dead and all(int(w["windows_received"]) == 0 for w in dead)


def test_windows_have_one_row_per_meter_per_slot():
    rows = _rows("windows_observed.csv")
    keys = {(w["meter_id"], w["slot_start"]) for w in rows}
    assert len(keys) == len(rows)


def test_generation_is_deterministic(tmp_path):
    a = generate(42, str(tmp_path / "a"))
    b = generate(42, str(tmp_path / "b"))
    shas_a = {k: v for k, v in a.items() if not k.endswith("rows")}
    shas_b = {k: v for k, v in b.items() if not k.endswith("rows")}
    assert shas_a == shas_b
