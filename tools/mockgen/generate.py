"""Mock month generator (A-T10). Synthetic data only, labelled "illustrative".

Writes the CSVs of contract/01 section 7 into an output folder (default contract/fixtures/mock_month).
Deterministic for a given --seed. Period: 2026-10-24 to 2026-11-22 (30 days), UTC times.

    python -m tools.mockgen.generate --seed 42 --out contract/fixtures/mock_month
"""
import argparse
import csv
import hashlib
import os
from datetime import datetime, timedelta, timezone

import numpy as np

from tools.mockgen.cities import CITIES, LIVE_VENUE, NAMED

START = datetime(2026, 10, 24, tzinfo=timezone.utc)
DAYS = 30
N_SONGS = 200
N_ARTISTS = 120
SLOT_MIN = 10          # windows_observed aggregated per 10 minutes
WINDOWS_EXPECTED = 10  # field mode: one 10 s window per minute
UTC_OFFSET_H = 1       # Cameroon is UTC+1; venue hours are local

SCENARIO_LOOP_SONG = "S-M0150"
SCENARIO_LOOP_VENUE = "V-DLA-AKWA01"
SCENARIO_PROMO_SONG = "S-M0077"
SCENARIO_POWERCUT_METER = "M-15"
SCENARIO_QUIET_VENUE = "V-YDE-BASTO1"

FILES = {
    "venues": ["venue_id", "name", "city", "lat", "lon", "size_class", "stratum", "bars_in_stratum", "open_hour", "close_hour"],
    "meters": ["meter_id", "venue_id", "catch_rate_true", "installed_at"],
    "songs": ["song_id", "title", "artist_name", "isrc", "duration_s", "popularity_rank"],
    "owners": ["song_id", "owner_name", "role", "share_pct", "momo"],
    "plays_true": ["true_play_id", "venue_id", "song_id", "started_at", "duration_s", "scenario"],
    "plays_observed": ["play_id", "venue_id", "meter_id", "song_id", "started_at", "duration_s", "loudness_db", "source", "scenario"],
    "windows": ["meter_id", "slot_start", "slot_minutes", "windows_received", "windows_expected", "mean_loudness_db"],
}


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _build_venues(rng):
    venues, meters = [], []
    size_names = ["S", "M", "L"]
    meter_no = 11
    for city, (lat, lon, n, prefix, bars) in CITIES.items():
        for i in range(n):
            vid = NAMED.get((city, i)) or f"V-{prefix}-{prefix[:3]}{i + 1:02d}"
            size = rng.choice(size_names, p=[0.5, 0.35, 0.15])
            jlat = lat + rng.uniform(-0.03, 0.03)
            jlon = lon + rng.uniform(-0.03, 0.03)
            open_h, close_h = 18, 2
            venues.append({
                "venue_id": vid, "name": f"Mock bar {city} {i + 1:02d}", "city": city,
                "lat": round(jlat, 4), "lon": round(jlon, 4), "size_class": size,
                "stratum": f"{prefix}-{size}", "bars_in_stratum": bars[size],
                "open_hour": open_h, "close_hour": close_h,
            })
            meters.append({
                "meter_id": f"M-{meter_no}", "venue_id": vid,
                "catch_rate_true": round(float(rng.uniform(0.70, 0.92)), 3),
                "installed_at": _iso(START - timedelta(days=int(rng.integers(5, 40)))),
            })
            meter_no += 1
    venues.append({
        "venue_id": LIVE_VENUE, "name": "CIMFEST demo table", "city": "Buea", "lat": 4.1527, "lon": 9.2410,
        "size_class": "S", "stratum": "BUEA-S", "bars_in_stratum": 150, "open_hour": 18, "close_hour": 2,
    })
    return venues, meters


def _build_songs(rng):
    ranks = np.arange(1, N_SONGS + 1)
    pop = 1.0 / ranks ** 1.05
    pop = pop / pop.sum()
    songs, owners = [], []
    artist_of = rng.integers(1, N_ARTISTS + 1, size=N_SONGS)
    for i in range(N_SONGS):
        sid = f"S-M{i + 1:04d}"
        dur = int(rng.integers(160, 331))
        songs.append({
            "song_id": sid, "title": f"Mock Song {i + 1:03d}", "artist_name": f"Mock Artist {artist_of[i]:02d}",
            "isrc": f"CM-SPF-26-{i + 1:05d}", "duration_s": dur, "popularity_rank": i + 1,
        })
        singer, composer, producer = 50.0, 30.0, 20.0
        owners.append({"song_id": sid, "owner_name": f"Mock Singer {artist_of[i]:02d}", "role": "singer",
                       "share_pct": singer, "momo": f"+2376990{int(rng.integers(0, 100000)):05d}"})
        owners.append({"song_id": sid, "owner_name": f"Mock Composer {artist_of[i]:02d}", "role": "composer",
                       "share_pct": composer, "momo": f"+2376990{int(rng.integers(0, 100000)):05d}"})
        owners.append({"song_id": sid, "owner_name": f"Mock Producer {artist_of[i]:02d}", "role": "producer",
                       "share_pct": producer, "momo": f"+2376990{int(rng.integers(0, 100000)):05d}"})
    return songs, owners, pop, {s["song_id"]: s["duration_s"] for s in songs}


def generate(seed: int, out_dir: str) -> dict:
    rng = np.random.default_rng(seed)
    venues, meters = _build_venues(rng)
    songs, owners, pop, dur_of = _build_songs(rng)
    song_ids = [s["song_id"] for s in songs]

    # venue taste: 70% global popularity, 30% a random preference per venue
    taste = {}
    for v in venues:
        rand = rng.dirichlet(np.full(N_SONGS, 0.3))
        taste[v["venue_id"]] = 0.7 * pop + 0.3 * rand

    catch = {m["meter_id"]: m["catch_rate_true"] for m in meters}
    meter_of = {m["venue_id"]: m["meter_id"] for m in meters}

    plays_true, plays_obs, windows = [], [], []
    seq = 0

    def add_play(venue_id, song_id, start, scenario):
        nonlocal seq
        seq += 1
        d = dur_of[song_id]
        plays_true.append({"true_play_id": f"TP-{seq:07d}", "venue_id": venue_id, "song_id": song_id,
                           "started_at": _iso(start), "duration_s": d, "scenario": scenario})
        mid = meter_of.get(venue_id)
        if mid is None or rng.uniform() > catch[mid]:
            return
        if mid == SCENARIO_POWERCUT_METER and _is_powercut(start):
            return
        size = next(v["size_class"] for v in venues if v["venue_id"] == venue_id)
        base = {"L": -14.0, "M": -21.0, "S": -28.0}[size]
        loud = round(base + rng.normal(0, 3), 1)
        plays_obs.append({"play_id": f"P-{seq:07d}", "venue_id": venue_id, "meter_id": mid, "song_id": song_id,
                          "started_at": _iso(start), "duration_s": d, "loudness_db": loud, "source": "mock",
                          "scenario": scenario})

    def _is_powercut(start):
        return start.date() in (datetime(2026, 11, 8).date(), datetime(2026, 11, 9).date())

    for day in range(DAYS):
        day0 = START + timedelta(days=day)
        weekday = day0.weekday()  # Mon=0 ... Sun=6
        factor = 1.4 if weekday in (4, 5) else (0.8 if weekday == 6 else 1.0)
        for v in venues:
            hours = [18, 19, 20, 21, 22, 23, 0, 1]
            for h in hours:
                local = day0 + timedelta(hours=h if h >= 18 else 24 + h)
                start_hour = local - timedelta(hours=UTC_OFFSET_H)
                n = int(round(rng.integers(13, 17) * factor))
                t = start_hour
                for _ in range(n):
                    sid = song_ids[rng.choice(N_SONGS, p=taste[v["venue_id"]])]
                    add_play(v["venue_id"], sid, t, "normal")
                    t = t + timedelta(seconds=dur_of[sid])
        # loop scenario: one song looped at V-DLA-AKWA01 on Fri/Sat 22:00-01:00
        if weekday in (4, 5):
            t = day0 + timedelta(hours=22 - UTC_OFFSET_H)
            for _ in range(12):
                add_play(SCENARIO_LOOP_VENUE, SCENARIO_LOOP_SONG, t, "loop")
                t = t + timedelta(seconds=dur_of[SCENARIO_LOOP_SONG] + 5)
        # quiet hours: one song at 04:00-05:00 to an empty room
        t = day0 + timedelta(hours=4 - UTC_OFFSET_H + 24)
        add_play(SCENARIO_QUIET_VENUE, song_ids[int(rng.integers(0, N_SONGS))], t, "quiet_hours")

    # promo: a new release rotated in 5 venues during the last 7 days
    last7 = range(DAYS - 7, DAYS)
    promo_venues = [v["venue_id"] for v in venues[:5]]
    for day in last7:
        for vid in promo_venues:
            for k in range(6):
                t = START + timedelta(days=day, hours=19 + k, minutes=int(rng.integers(0, 50)))
                add_play(vid, SCENARIO_PROMO_SONG, t, "promo")

    # windows: per meter per 10 min slot
    for m in meters:
        for slot in range(DAYS * 24 * 60 // SLOT_MIN):
            ts = START + timedelta(minutes=slot * SLOT_MIN)
            received = WINDOWS_EXPECTED
            if m["meter_id"] == SCENARIO_POWERCUT_METER and _is_powercut(ts):
                received = 0
            elif rng.uniform() < 0.03:
                received = int(rng.integers(3, WINDOWS_EXPECTED))
            windows.append({"meter_id": m["meter_id"], "slot_start": _iso(ts), "slot_minutes": SLOT_MIN,
                            "windows_received": received, "windows_expected": WINDOWS_EXPECTED,
                            "mean_loudness_db": round(float(rng.normal(-22, 4)), 1)})

    os.makedirs(out_dir, exist_ok=True)
    write = {
        "venues": venues, "meters": meters, "songs": songs, "owners": owners,
        "plays_true": plays_true, "plays_observed": plays_obs, "windows": windows,
    }
    hashes = {}
    for name, rows in write.items():
        path = os.path.join(out_dir, f"{name}.csv" if name != "windows" else "windows_observed.csv")
        if name == "plays_true":
            path = os.path.join(out_dir, "plays_true.csv")
        elif name == "plays_observed":
            path = os.path.join(out_dir, "plays_observed.csv")
        elif name == "venues":
            path = os.path.join(out_dir, "venues.csv")
        elif name == "meters":
            path = os.path.join(out_dir, "meters.csv")
        elif name == "songs":
            path = os.path.join(out_dir, "songs_synthetic.csv")
        elif name == "owners":
            path = os.path.join(out_dir, "owners_synthetic.csv")
        with open(path, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=FILES[name], lineterminator="\n")
            w.writeheader()
            w.writerows(rows)
        with open(path, "rb") as fh:
            hashes[os.path.basename(path)] = hashlib.sha256(fh.read()).hexdigest()
        hashes[os.path.basename(path) + " rows"] = len(rows)
    _write_scenarios(out_dir)
    return hashes


def _write_scenarios(out_dir: str) -> None:
    text = """# Mock month scenarios (illustrative numbers, synthetic data)

Period: 2026-10-24 to 2026-11-22 (30 days). All numbers are generated, not measured.

1. loop: song S-M0150 (low popularity) looped at V-DLA-AKWA01 on Fridays and Saturdays, 22:00-01:00, about 12 plays a night. SoundProof's rules should cut its counted plays.
2. promo: song S-M0077 rotated in 5 venues (6 plays a day each) during the last 7 days. The plays are real, but bought.
3. power_cut: meter M-15 has no windows on 8 and 9 November 2026. Its listening fraction drops.
4. quiet_hours: venue V-YDE-BASTO1 plays one song from 04:00 to 05:00 each night to an empty room (quiet loudness).
5. moved_meter: not modelled in this month (no cell_id column). The flag is tested with live data only.

Venue sizes: S/M/L about 50/35/15%. bars_in_stratum values are illustrative, not from any source.
"""
    with open(os.path.join(out_dir, "scenarios.md"), "w", encoding="utf-8") as fh:
        fh.write(text)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="mock month generator (A-T10)")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out", default=os.path.join("contract", "fixtures", "mock_month"))
    args = p.parse_args(argv)
    info = generate(args.seed, args.out)
    for k, v in info.items():
        print(f"{k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
