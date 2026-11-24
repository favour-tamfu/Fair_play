"""Write contract/fixtures/api/*.json + feed_sample.txt: FAKE but self-consistent read-API responses for A's web
(`?mock=1`). Every file must validate against contract/schemas (server/tests/test_api_fixtures.py).

    python -m server.tools.make_api_fixtures

Song titles and artists are real catalogue entries (tools/mockgen/real_songs.csv); the looping song is a fictional
test track. Bars, plays and every number are illustrative, never for the pitch.
Deterministic (seeded): re-running gives identical files.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from fairplay_core.schema import format_utc

OUT = Path(__file__).resolve().parents[2] / "contract" / "fixtures" / "api"
POT = 100_000_000
NOW = datetime(2026, 11, 24, 21, 30, tzinfo=timezone.utc)
rng = np.random.default_rng(2026)

CITIES = {"Douala": (4.0511, 9.7679), "Yaounde": (3.8480, 11.5021), "Buea": (4.1527, 9.2410),
          "Limbe": (4.0186, 9.2043), "Bamenda": (5.9631, 10.1591), "Bafoussam": (5.4778, 10.4176),
          "Garoua": (9.3014, 13.3977), "Kribi": (2.9395, 9.9095)}
VENUES = [  # venue_id, name, city, size
    ("V-BUEA-CIMFEST", "CIMFEST demo table", "Buea", "S"),
    ("V-DLA-AKWA01", "Mock Bar Akwa 1", "Douala", "L"), ("V-DLA-BONAP1", "Mock Bar Bonapriso 1", "Douala", "M"),
    ("V-DLA-DEIDO1", "Mock Bar Deido 1", "Douala", "S"), ("V-DLA-NDKOT1", "Mock Bar Ndokoti 1", "Douala", "M"),
    ("V-YDE-BASTO1", "Mock Bar Bastos 1", "Yaounde", "L"), ("V-YDE-MVAN01", "Mock Bar Mvan 1", "Yaounde", "S"),
    ("V-YDE-ESSOS1", "Mock Bar Essos 1", "Yaounde", "M"), ("V-YDE-NLONG1", "Mock Bar Nlongkak 1", "Yaounde", "S"),
    ("V-BUEA-MOLYK1", "Mock Bar Molyko 1", "Buea", "M"), ("V-LMB-DOWN01", "Mock Bar Down Beach 1", "Limbe", "S"),
    ("V-BDA-CMMC01", "Mock Bar Commercial Ave 1", "Bamenda", "M"), ("V-BFS-MARC01", "Mock Bar Marche A 1", "Bafoussam", "S"),
    ("V-GRA-CENT01", "Mock Bar Centre 1", "Garoua", "S"), ("V-KRI-PLAG01", "Mock Bar Plage 1", "Kribi", "S"),
]
BARS = {("Douala", "S"): 4250, ("Douala", "M"): 2975, ("Douala", "L"): 1275, ("Yaounde", "S"): 3250,
        ("Yaounde", "M"): 2275, ("Yaounde", "L"): 975}
METERS = {"V-BUEA-CIMFEST": "M-07", "V-DLA-AKWA01": "M-11", "V-YDE-BASTO1": "M-12", "V-BUEA-MOLYK1": "M-13"}
LOOP_SONG, LOOP_VENUE = "S-M0015", "V-DLA-AKWA01"
LOOP_TEST_TRACK = ("Loop test track", "Fair Play test artist")
REAL_SONGS = Path(__file__).resolve().parents[2] / "tools" / "mockgen" / "real_songs.csv"
REAL_ARTISTS = ("Locko", "Mr. Leo", "Magasco", "Kocee", "Blanche Bailly", "Charlotte Dipanda", "Mink's", "Lady Ponce",
                "Salatiel", "Tenor", "Stanley Enow", "X-Maleya")


def _real_titles() -> dict[str, list[str]]:
    """Titles of each real artist, in catalogue order."""
    import csv
    out: dict[str, list[str]] = {}
    with open(REAL_SONGS, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out.setdefault(r["artist_name"], []).append(r["title"])
    return out


def largest_remainder(total: int, weights: list[float]) -> list[int]:
    w = np.asarray(weights, float)
    raw = total * w / w.sum()
    out = np.floor(raw).astype(int)
    out[np.argsort(-(raw - out), kind="stable")[: total - out.sum()]] += 1
    return out.tolist()


def ts(minutes_ago: float) -> str:
    return format_utc(NOW - timedelta(minutes=minutes_ago))


def build() -> dict[str, object]:
    global rng
    rng = np.random.default_rng(2026)   # fresh every call → identical output
    # ---------------------------------------------------------------- venues + meters
    venues, n = [], 14
    for vid, name, city, size in VENUES:
        lat, lon = CITIES[city]
        if vid != "V-BUEA-CIMFEST":
            lat, lon = lat + rng.uniform(-0.03, 0.03), lon + rng.uniform(-0.03, 0.03)
        mid = METERS.get(vid) or f"M-{n:02d}"
        n += vid not in METERS
        online = vid in METERS or rng.random() > 0.2
        venues.append({"venue_id": vid, "name": name, "city": city, "lat": round(lat, 4), "lon": round(lon, 4),
                       "stratum": f"{city.upper()[:4]}-{size}", "bars_in_stratum": BARS.get((city, size), 300),
                       "meters": [{"meter_id": mid, "online": bool(online), "last_seen": ts(rng.uniform(0, 2) if online else 300),
                                   "queued": 0 if online else int(rng.integers(5, 40)),
                                   "catch_rate": round(float(rng.uniform(0.72, 0.9)), 2)}]})
    meter_of = {v["venue_id"]: v["meters"][0]["meter_id"] for v in venues}

    # ---------------------------------------------------------------- songs (mock catalogue) + uploads
    # Real titles and artists from the verified catalogue (A, tools/mockgen/real_songs.csv); plays and numbers stay
    # illustrative. The looping song is a fictional test track so no real artist is shown looping plays.
    artists = list(REAL_ARTISTS)
    titles_of = _real_titles()
    used = {a: 0 for a in artists}
    songs = []
    for i in range(1, 21):
        dur = int(rng.integers(160, 330))
        if f"S-M{i:04d}" == LOOP_SONG:
            title, artist = LOOP_TEST_TRACK
        else:
            artist = artists[(i - 1) % 12]
            title = titles_of[artist][used[artist]]
            used[artist] += 1
        songs.append({"song_id": f"S-M{i:04d}", "title": title, "artist_name": artist,
                      "isrc": f"CM-SPF-26-{i:05d}", "duration_s": dur})
    artists.append(LOOP_TEST_TRACK[1])
    by_id = {s["song_id"]: s for s in songs}

    # ---------------------------------------------------------------- plays (newest first)
    plays = []
    for k in range(30):
        loop = k % 5 == 0
        s = by_id[LOOP_SONG] if loop else songs[int(min(rng.zipf(1.6), 20)) - 1]
        vid = LOOP_VENUE if loop else VENUES[int(rng.integers(0, len(VENUES)))][0]
        src = "live" if vid == "V-BUEA-CIMFEST" else ("virtual" if vid in METERS else "mock")
        # loop song plays at k = 25, 20, 15, 10, 5, 0 (oldest → newest): sr-1.0 gives 1, 1, 0.5, 0.25, 0, 0
        loop_rule = {25: (1.0, "streak_1"), 20: (1.0, "streak_2"), 15: (0.5, "streak_3"), 10: (0.25, "streak_4"),
                     5: (0.0, "cooldown"), 0: (0.0, "cooldown")}
        w, why = loop_rule[k] if loop else (1.0, "streak_1")
        weight, reasons = [w], [why] + (["loop"] if loop else [])
        plays.append({"play_id": f"P-{rng.integers(0, 16**12):012x}", "venue_id": vid, "meter_id": meter_of[vid],
                      "song_id": s["song_id"], "title": s["title"], "artist_name": s["artist_name"],
                      "started_at": ts(4 + 4 * k), "duration_s": float(s["duration_s"]), "source": src,
                      "weight": weight[0], "reasons": reasons})

    # ---------------------------------------------------------------- shares raw vs standardised
    base = np.array([60 / (i ** 1.05) for i in range(1, 21)])
    raw_plays = np.round(base * rng.uniform(0.8, 1.2, 20)).astype(int) + 2
    loop_idx = 14
    raw_plays[loop_idx] = 96                                      # looping artist: #1 in raw counts
    weighted = raw_plays * rng.uniform(0.85, 0.97, 20)
    weighted[loop_idx] = 11.25                                    # neutralised by cooldown

    def shares(counts, mode):
        sh = counts / counts.sum()
        amounts = largest_remainder(POT, sh.tolist())
        rows = []
        for i in np.argsort(-sh, kind="stable"):
            s = songs[i]
            half = 0.0                                   # D-011: full coverage -> no sampling range
            flags = ["loop", "cooldown"] if i == loop_idx and mode == "standardised" else (["loop"] if i == loop_idx else [])
            rows.append({"song_id": s["song_id"], "title": s["title"], "artist_name": s["artist_name"],
                         "raw_plays": int(raw_plays[i]), "weighted_plays": round(float(counts[i]), 2),
                         "share": round(float(sh[i]), 5), "ci_low": round(float(max(sh[i] - half, 0)), 5),
                         "ci_high": round(float(min(sh[i] + half, 1)), 5), "amount_fcfa": amounts[i], "flags": flags})
        return {"stats_run_id": "R-20261124213000", "rule_version": "sr-1.0" if mode == "standardised" else "raw",
                "pot_fcfa": POT, "escrow_share": 0.0, "rows": rows}

    shares_std = shares(weighted, "standardised")
    shares_raw = shares(raw_plays.astype(float), "raw")

    # ---------------------------------------------------------------- owners + payouts (from standardised amounts)
    owners_of, payout_rows = {}, []
    for r in shares_std["rows"]:
        s = by_id[r["song_id"]]
        num = int(s["song_id"][-4:])
        owners = [{"name": s["artist_name"], "role": "singer", "share_pct": 50, "momo": f"+2376990{num:02d}001"},
                  {"name": "Composer not yet declared", "role": "composer", "share_pct": 30, "momo": f"+2376990{num:02d}002"},
                  {"name": "Producer not yet declared", "role": "producer", "share_pct": 20, "momo": f"+2376990{num:02d}003"}]
        owners_of[s["song_id"]] = owners
        for o, amt in zip(owners, largest_remainder(r["amount_fcfa"], [o["share_pct"] for o in owners])):
            payout_rows.append({"owner_name": o["name"], "role": o["role"], "song_id": s["song_id"], "title": s["title"],
                                "amount_fcfa": amt, "momo": o["momo"], "status": "sent_mock"})
    payouts = {"pot_fcfa": POT, "frozen": False, "rows": payout_rows, "total_fcfa": sum(p["amount_fcfa"] for p in payout_rows)}

    # ---------------------------------------------------------------- catalogue (uploads) for the portal
    up = {a: titles_of[a][used[a]] for a in REAL_ARTISTS[:4]}        # each artist's next song, not used above
    uploads = [(up["Locko"], "Locko", "ready", None, 4211), (up["Mr. Leo"], "Mr. Leo", "ready", None, 3890),
               (f'{up["Locko"]} (copy)', "Locko", "duplicate_suspected", "S-000001", 0),
               (up["Magasco"], "Magasco", "processing", None, 0), (up["Kocee"], "Kocee", "failed", None, 0)]
    songs_list = [{"song_id": f"S-{i:06d}", "title": t, "artist_name": a, "isrc": None, "iswc": None,
                   "duration_s": 212.0 if st != "failed" else None, "status": st, "n_hashes": nh,
                   "uploaded_at": ts(90 - 10 * i), "duplicate_of": dup} for i, (t, a, st, dup, nh) in enumerate(uploads, 1)]
    song_detail = {**songs_list[0], "owners": [
        {"name": "Locko", "role": "singer", "share_pct": 50, "momo": "+237699000001"},
        {"name": "Composer not yet declared", "role": "composer", "share_pct": 30, "momo": "+237699000002"},
        {"name": "Producer not yet declared", "role": "producer", "share_pct": 20, "momo": "+237699000003"}]}

    # ---------------------------------------------------------------- flags, ledger, overview, compare
    flags = [
        {"flag_id": 1, "type": "loop", "song_id": LOOP_SONG, "venue_id": LOOP_VENUE,
         "detail": "12 consecutive plays, gaps = song length ±20 s (Fri 22:00–01:00)", "created_at": ts(60)},
        {"flag_id": 2, "type": "cooldown", "song_id": LOOP_SONG, "venue_id": LOOP_VENUE,
         "detail": "8 plays counted 0 (cooldown after 4th play)", "created_at": ts(60)},
        {"flag_id": 3, "type": "concentration", "song_id": "S-M0007", "venue_id": None,
         "detail": "heard in 3 venues; top 2 hold 72% of weighted plays — capped", "created_at": ts(58)},
        {"flag_id": 4, "type": "duplicate_suspected", "song_id": "S-000003", "venue_id": None,
         "detail": "upload matches S-000001 in 3/3 slices", "created_at": ts(50)},
        {"flag_id": 5, "type": "clock_skew", "song_id": None, "venue_id": "V-YDE-MVAN01",
         "detail": "meter clock 7.2 s behind server", "created_at": ts(20)},
    ]
    anchor = {"hour": format_utc(NOW.replace(minute=0)), "root": f"{rng.integers(0, 2**63):016x}" * 4, "via": "file",
              "tx_ref": None}
    ledger = {"intact": True, "broken_at_play_id": None, "plays_checked": 1287, "last_root": anchor["root"],
              "last_anchor": anchor}
    overview = {"meters_online": sum(v["meters"][0]["online"] for v in venues), "meters_total": len(venues),
                "venues": len(venues), "plays_raw": int(raw_plays.sum()), "plays_counted": round(float(weighted.sum()), 2),
                "songs_ready": 2, "unidentified_music_min": 0.0, "rule_version": "sr-1.0", "ledger_intact": True,
                "last_anchor": anchor}
    n_art = len(artists)
    compare = {"pot_fcfa": POT, "n_artists": n_art, "flat_each_fcfa": POT // n_art,
               "misallocated_flat_fcfa": 31_400_000, "misallocated_fairplay_fcfa": 4_100_000, "basis": "mock_month_truth"}

    # ---------------------------------------------------------------- artists
    artist_list = [{"artist_name": a, "songs": [s["song_id"] for s in songs if s["artist_name"] == a]} for a in artists]
    a1 = artists[0]
    a1_plays = [p for p in plays if p["artist_name"] == a1]
    pv = {}
    for p in a1_plays:
        d = pv.setdefault(p["venue_id"], {"plays_raw": 0, "plays_counted": 0.0})
        d["plays_raw"] += 1
        d["plays_counted"] += p["weight"]
    vname = {v["venue_id"]: (v["name"], v["city"]) for v in venues}
    a1_rows = [r for r in shares_std["rows"] if r["artist_name"] == a1]
    artist = {"artist_name": a1, "songs": [{"song_id": s["song_id"], "title": s["title"]} for s in songs if s["artist_name"] == a1],
              "plays_by_venue": [{"venue_id": k, "name": vname[k][0], "city": vname[k][1], **v} for k, v in pv.items()],
              "plays_by_day": [{"date": (NOW - timedelta(days=d)).strftime("%Y-%m-%d"), "plays_raw": int(r),
                                "plays_counted": float(r) * 0.9} for d, r in zip(range(6, -1, -1), rng.integers(3, 15, 7))],
              "amount_fcfa": sum(r["amount_fcfa"] for r in a1_rows), "recent": a1_plays[:10]}

    # ---------------------------------------------------------------- live feed sample (raw SSE text)
    p0 = plays[0]
    events = [
        ("batch", {"meter_id": "M-07", "venue_id": "V-BUEA-CIMFEST", "seq": 1842, "window_start": ts(1.0), "late": False}),
        ("meter", {"meter_id": "M-07", "online": True, "queued": 0, "last_seen": ts(0.9)}),
        ("match", {"meter_id": "M-07", "venue_id": "V-BUEA-CIMFEST", "song_id": p0["song_id"], "title": p0["title"],
                   "offset_s": 42.3, "confidence": 0.31, "accepted": True, "window_start": ts(1.0)}),
        ("batch", {"meter_id": "M-07", "venue_id": "V-BUEA-CIMFEST", "seq": 1843, "window_start": ts(0.83), "late": False}),
        ("match", {"meter_id": "M-07", "venue_id": "V-BUEA-CIMFEST", "song_id": p0["song_id"], "title": p0["title"],
                   "offset_s": 52.3, "confidence": 0.28, "accepted": True, "window_start": ts(0.83)}),
        ("play", {"play_id": p0["play_id"], "venue_id": "V-BUEA-CIMFEST", "song_id": p0["song_id"], "title": p0["title"],
                  "artist_name": p0["artist_name"], "started_at": ts(1.7), "source": "live"}),
        ("batch", {"meter_id": "M-11", "venue_id": "V-DLA-AKWA01", "seq": 77, "window_start": ts(30), "late": True}),
        ("flag", flags[1]),
        ("ledger", {"intact": True, "broken_at_play_id": None}),
        ("stats", {"stats_run_id": "R-20261124213000"}),
        ("meter", {"meter_id": "M-14", "online": False, "queued": 23, "last_seen": ts(12)}),
    ]
    feed = "".join(f"event: {e}\ndata: {json.dumps(d, ensure_ascii=False)}\n\n" for e, d in events)
    feed = ": keep-alive\n\n" + feed

    return {"overview.json": overview, "venues.json": venues, "plays.json": plays,
            "shares_standardised.json": shares_std, "shares_raw.json": shares_raw, "flags.json": flags,
            "payouts.json": payouts, "compare_flat.json": compare, "ledger_status.json": ledger,
            "artists.json": artist_list, "artist.json": artist, "songs.json": songs_list, "song.json": song_detail,
            "song_upload_response.json": {"song_id": "S-000006", "status": "uploaded"}, "feed_sample.txt": feed}


SCHEMA_OF = {"overview.json": "overview", "venues.json": "venues", "plays.json": "plays",
             "shares_standardised.json": "shares", "shares_raw.json": "shares", "flags.json": "flags",
             "payouts.json": "payouts", "compare_flat.json": "compare_flat", "ledger_status.json": "ledger_status",
             "artists.json": "artists", "artist.json": "artist", "songs.json": "songs", "song.json": "song",
             "song_upload_response.json": "song_upload_response"}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, doc in build().items():
        text = doc if isinstance(doc, str) else json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
        (OUT / name).write_bytes(text.encode("utf-8"))
        print(f"wrote {name}")


if __name__ == "__main__":
    main()
