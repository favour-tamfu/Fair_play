"""Generate a mock month that uses the REAL song catalogue (Person B's decision, 2026-11-24) — same CSV format as
contract §7, so `server.tools.import_mock` loads it unchanged.

    python -m server.tools.catalogue_month [--songs S-000013..S-000195] [--seed 20261124] [--out data/mock_month_catalogue]
    python -m server.tools.import_mock data/mock_month_catalogue

Bars and meters: A's venues.csv / meters.csv (hours, size, catch rates) are reused as they are (read only).
Songs: the uploaded catalogue songs in the --songs range (title, artist, measured length from the songs table);
the songs keep their own rows, the mock month only adds plays for them. No owners are written (none are known).
Everything else is random (seeded, so the same seed gives the same month):
  - popularity: random order of the songs, Zipf-like weights × random noise; every bar has its own favourites
  - nights: bars open with a probability by size (S 70 %, M 85 %, L 95 %, more on Fri/Sat); songs back to back
    from the bar's local opening to closing hour, 0-45 s gaps, the same song never twice in a row by chance
  - observed plays: each true play is caught with the meter's catch_rate_true; none during a power cut
  - loudness per bar and per play; 10-minute window slots for every meter
Scenarios (written to scenarios.md with the songs and bars drawn):
  loop        a low-popularity song repeated back to back 5-6 times, twice a night, Fri/Sat, at one bar
  promo       a mid-popularity song 6 extra times a night in 5 bars during the last 7 days
  quiet_hours one bar plays one song from 04:00 to 05:00 local each night to an empty room (quiet)
  power_cut   one meter sends nothing for 2 days
All times UTC in the files; bar hours are local (Cameroon = UTC+1).
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from server import config
from server.db import connect

UTC = timezone.utc
A_DIR = config.ROOT / "contract" / "fixtures" / "mock_month"
DEFAULT_OUT = config.ROOT / "data" / "mock_month_catalogue"
START = datetime(2026, 10, 24, tzinfo=UTC)          # contract §7: 30 days, 2026-10-24 → 2026-11-22
DAYS = 30
LOCAL = timedelta(hours=config.LOCAL_UTC_OFFSET_H)
OPEN_P = {"S": 0.70, "M": 0.85, "L": 0.95}


def iso(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def load_songs(conn, lo: str, hi: str) -> pd.DataFrame:
    rows = conn.execute("""SELECT song_id, title, artist_name, isrc, duration_s FROM songs
                           WHERE song_id BETWEEN %s AND %s AND status = 'ready' AND source = 'upload'
                           ORDER BY song_id""", (lo, hi)).fetchall()
    return pd.DataFrame(rows, columns=["song_id", "title", "artist_name", "isrc", "duration_s"])


def generate(songs: pd.DataFrame, venues: pd.DataFrame, meters: pd.DataFrame, seed: int = 20261124,
             days: int = DAYS) -> dict:
    rng = np.random.default_rng(seed)
    ids = songs["song_id"].to_numpy()
    n = len(ids)
    if n < 4:
        raise ValueError("need at least 4 songs")
    length = dict(zip(ids, songs["duration_s"].astype(float).round(0)))
    order = rng.permutation(n)                                     # order[k] = index of the song with rank k+1
    rank = np.empty(n, int)
    rank[order] = np.arange(1, n + 1)
    base = rank ** -0.8 * rng.lognormal(0, 0.25, n)
    meter_of = dict(zip(meters["venue_id"], meters["meter_id"]))
    catch = dict(zip(meters["meter_id"], meters["catch_rate_true"].astype(float)))
    vlist = [v for v in venues.itertuples(index=False) if v.venue_id in meter_of]

    loop_song = ids[order[int(n * 0.8)]]
    promo_song = ids[order[int(n * 0.4)]]
    quiet_song = ids[order[int(n * 0.6)]]
    loop_venue = vlist[int(rng.integers(len(vlist)))].venue_id
    others = [v.venue_id for v in vlist if v.venue_id != loop_venue]
    promo_venues = set(rng.choice(others, size=min(5, len(others)), replace=False))
    quiet_venue = next((v for v in others if v not in promo_venues), loop_venue)
    cut_meter = meter_of[others[int(rng.integers(len(others)))]]
    cut_day = int(rng.integers(5, max(6, days - 3)))
    cut = (START + timedelta(days=cut_day), START + timedelta(days=cut_day + 2))
    promo_from = START + timedelta(days=days - 7)

    true, obs = [], []
    loud_base = {}
    for v in vlist:
        w = base * rng.lognormal(0, 0.5, n)                       # local favourites
        p = w / w.sum()
        loud_base[v.venue_id] = float(rng.normal(-24, 2.5))
        m = meter_of[v.venue_id]
        open_h = int(v.open_hour) if str(v.open_hour) not in ("", "nan") else 18
        close_h = int(v.close_hour) if str(v.close_hour) not in ("", "nan") else 2
        for d in range(days):
            day = START + timedelta(days=d)
            weekend = (day + LOCAL).weekday() in (4, 5)
            if rng.random() > min(0.99, OPEN_P.get(v.size_class, 0.8) + (0.1 if weekend else 0)):
                continue
            t = day + timedelta(hours=open_h) - LOCAL + timedelta(minutes=float(rng.uniform(0, 40)))
            end = day + timedelta(hours=close_h + (24 if close_h <= open_h else 0)) - LOCAL
            plan = []                                              # (song, scenario)
            last = None
            loop_nights = v.venue_id == loop_venue and weekend
            loop_at = sorted(rng.choice(np.arange(6, 30), size=2, replace=False)) if loop_nights else []
            promo_left = 6 if (v.venue_id in promo_venues and day >= promo_from) else 0
            while True:
                k = len(plan)
                if loop_at and k == loop_at[0]:
                    loop_at.pop(0)
                    plan += [(loop_song, "loop")] * int(rng.integers(5, 7))
                    last = loop_song
                    continue
                if promo_left and rng.random() < 0.25:
                    promo_left -= 1
                    s, scen = promo_song, "promo"
                else:
                    s = ids[rng.choice(n, p=p)]
                    while s == last:
                        s = ids[rng.choice(n, p=p)]
                    scen = "normal"
                plan.append((s, scen))
                last = s
                if len(plan) > 200:
                    break
            for s, scen in plan:
                if t >= end:
                    break
                true.append((v.venue_id, m, s, t, length[s], scen))
                t += timedelta(seconds=length[s] + float(rng.uniform(0, 3) if scen == "loop" else rng.uniform(0, 45)))  # repeat button: no gap
            if v.venue_id == quiet_venue:                         # 04:00-05:00 local, empty room
                q = day + timedelta(days=1, hours=4) - LOCAL
                while q < day + timedelta(days=1, hours=5) - LOCAL:
                    true.append((v.venue_id, m, quiet_song, q, length[quiet_song], "quiet_hours"))
                    q += timedelta(seconds=length[quiet_song] + 2)

    true.sort(key=lambda r: (r[3], r[0]))
    plays_true, plays_obs = [], []
    for i, (vid, m, s, t, dur, scen) in enumerate(true, 1):
        plays_true.append((f"TP-{i:07d}", vid, s, iso(t), int(dur), scen))
        if cut[0] <= t < cut[1] and m == cut_meter:
            continue
        if rng.random() < catch[m]:
            db = -40.0 + rng.normal(0, 1.5) if scen == "quiet_hours" else loud_base[vid] + rng.normal(0, 1.5)
            plays_obs.append((f"P-{len(plays_obs) + 1:07d}", vid, m, s, iso(t), int(dur), round(float(db), 1), "mock",
                              scen))

    # 10-minute window slots: received unless power cut; loudness = bar level while music plays, else quiet
    busy = {}
    for vid, m, s, t, dur, scen in true:
        k = int((t - START).total_seconds() // 600)
        busy[(m, k)] = -40.0 if scen == "quiet_hours" else loud_base[vid]
    slots = []
    for m in sorted(set(meter_of.values())):
        for k in range(days * 144):
            t = START + timedelta(minutes=10 * k)
            off = m == cut_meter and cut[0] <= t < cut[1]
            lvl = busy.get((m, k), -45.0)
            slots.append((m, iso(t), 10, 0 if off else 60, 60,
                          "" if off else round(float(lvl + rng.normal(0, 1.0)), 1)))

    song_rows = [(r.song_id, r.title, r.artist_name, r.isrc or "", int(round(length[r.song_id])), int(rank[i]))
                 for i, r in enumerate(songs.itertuples(index=False))]
    title = dict(zip(songs["song_id"], songs["title"] + " by " + songs["artist_name"]))
    scen_md = f"""# Mock month on the real catalogue (generated by server/tools/catalogue_month.py, seed {seed})

Period: {iso(START)[:10]} to {iso(START + timedelta(days=days - 1))[:10]} ({days} days). Bars and meters: A's venues.csv / meters.csv.
Songs: {n} catalogue songs ({songs['artist_name'].nunique()} artists). All plays and numbers are generated, not measured.

1. loop: {loop_song} ({title[loop_song]}) repeated back to back 5-6 times, twice a night, Fri/Sat at {loop_venue}.
2. promo: {promo_song} ({title[promo_song]}) about 6 extra plays a night in {', '.join(sorted(promo_venues))}, last 7 days.
3. quiet_hours: {quiet_venue} plays {quiet_song} ({title[quiet_song]}) 04:00-05:00 local each open night, empty room (about -40 dB).
4. power_cut: meter {cut_meter} sends nothing from {iso(cut[0])} to {iso(cut[1])}.
True plays {len(plays_true)}, observed {len(plays_obs)}.
"""
    return {"songs": song_rows, "plays_true": plays_true, "plays_observed": plays_obs, "slots": slots,
            "scenarios_md": scen_md,
            "scenario": {"loop": (loop_song, loop_venue), "promo": (promo_song, sorted(promo_venues)),
                         "quiet_hours": (quiet_song, quiet_venue), "power_cut": (cut_meter, iso(cut[0]))}}


def write(out: Path, g: dict, venues_csv: Path, meters_csv: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "venues.csv").write_bytes(venues_csv.read_bytes())
    (out / "meters.csv").write_bytes(meters_csv.read_bytes())

    def w(name, header, rows):
        with open(out / name, "w", newline="", encoding="utf-8") as f:
            cw = csv.writer(f, lineterminator="\n")
            cw.writerow(header)
            cw.writerows(rows)
    w("songs_synthetic.csv", ["song_id", "title", "artist_name", "isrc", "duration_s", "popularity_rank"], g["songs"])
    w("owners_synthetic.csv", ["song_id", "owner_name", "role", "share_pct", "momo"], [])
    w("plays_true.csv", ["true_play_id", "venue_id", "song_id", "started_at", "duration_s", "scenario"], g["plays_true"])
    w("plays_observed.csv", ["play_id", "venue_id", "meter_id", "song_id", "started_at", "duration_s", "loudness_db",
                             "source", "scenario"], g["plays_observed"])
    w("windows_observed.csv", ["meter_id", "slot_start", "slot_minutes", "windows_received", "windows_expected",
                               "mean_loudness_db"], g["slots"])
    (out / "scenarios.md").write_text(g["scenarios_md"], "utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--songs", default="..".join(config.CATALOGUE_RANGE), help="song_id range lo..hi of the catalogue to use")
    ap.add_argument("--seed", type=int, default=20261124)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    a = ap.parse_args(argv)
    lo, hi = a.songs.split("..")
    with connect() as conn:
        songs = load_songs(conn, lo, hi)
    venues = pd.read_csv(A_DIR / "venues.csv", dtype=str, keep_default_na=False)
    meters = pd.read_csv(A_DIR / "meters.csv", dtype=str, keep_default_na=False)
    g = generate(songs, venues, meters, a.seed)
    write(a.out, g, A_DIR / "venues.csv", A_DIR / "meters.csv")
    print(g["scenarios_md"])
    print(f"written to {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
