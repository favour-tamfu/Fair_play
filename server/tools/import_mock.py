"""Import A's mock month (contract §7) — B-T11.

    python -m server.tools.import_mock [contract/fixtures/mock_month] [--no-stats]

One transaction. Re-import is safe: every mock row is wiped first (D-013), the live data and the live ledger chain
are never touched.
  venues.csv            -> venues (source mock; venues that already exist, e.g. the live venue, keep their source
                           and only get the descriptive fields: name, city, lat/lon, size, stratum)
  meters.csv            -> mock_meters (all 30, catch_rate = catch_rate_true: emulates calibrated meters) and
                           meters (source mock) for IDs not already used by a live/virtual meter
  songs_synthetic.csv   -> songs (source mock, status ready, no hashes) + owners_synthetic.csv -> owners;
                           ids already in the catalogue (e.g. catalogue_month.py) are used as they are
  plays_observed.csv    -> plays (source mock, chain 'mock'), hash-chained in time order from their own genesis
  windows_observed.csv  -> window_slots (10-minute aggregates, stored as they are)
  plays_true.csv        -> mock_truth (ground truth for compare-flat only)
Then runs stats for period mock_month (raw + standardised) unless --no-stats.
"""
from __future__ import annotations

import argparse
import logging
import math
import time
from pathlib import Path

import pandas as pd

from server import config
from server.db import connect
from server.ledger import chain

log = logging.getLogger("import_mock")
DEFAULT_DIR = config.ROOT / "contract" / "fixtures" / "mock_month"

COLUMNS = {
    "venues.csv": ["venue_id", "name", "city", "lat", "lon", "size_class", "stratum", "bars_in_stratum", "open_hour",
                   "close_hour"],
    "meters.csv": ["meter_id", "venue_id", "catch_rate_true", "installed_at"],
    "songs_synthetic.csv": ["song_id", "title", "artist_name", "isrc", "duration_s", "popularity_rank"],
    "owners_synthetic.csv": ["song_id", "owner_name", "role", "share_pct", "momo"],
    "plays_true.csv": ["true_play_id", "venue_id", "song_id", "started_at", "duration_s", "scenario"],
    "plays_observed.csv": ["play_id", "venue_id", "meter_id", "song_id", "started_at", "duration_s", "loudness_db",
                           "source", "scenario"],
    "windows_observed.csv": ["meter_id", "slot_start", "slot_minutes", "windows_received", "windows_expected",
                             "mean_loudness_db"],
}


class MockDataError(ValueError):
    pass


def read(folder: Path) -> dict[str, pd.DataFrame]:
    d = {}
    for name, cols in COLUMNS.items():
        df = pd.read_csv(folder / name, dtype=str, keep_default_na=False)
        missing = [c for c in cols if c not in df.columns]
        if missing:
            raise MockDataError(f"{name}: missing columns {missing}")
        d[name] = df[cols]
    v, m, s, o = d["venues.csv"], d["meters.csv"], d["songs_synthetic.csv"], d["owners_synthetic.csv"]
    po, pt = d["plays_observed.csv"], d["plays_true.csv"]
    if "V-BUEA-CIMFEST" not in set(v["venue_id"]):
        raise MockDataError("venues.csv must include the live venue V-BUEA-CIMFEST (contract §7)")
    for what, ids, known in (("meters.venue_id", m["venue_id"], v["venue_id"]),
                             ("plays_observed.meter_id", po["meter_id"], m["meter_id"]),
                             ("plays_observed.venue_id", po["venue_id"], v["venue_id"]),
                             ("plays_observed.song_id", po["song_id"], s["song_id"]),
                             ("plays_true.song_id", pt["song_id"], s["song_id"]),
                             ("owners.song_id", o["song_id"], s["song_id"])):
        bad = sorted(set(ids) - set(known))
        if bad:
            raise MockDataError(f"{what}: unknown ids {bad[:5]}")
    if po["play_id"].duplicated().any():
        raise MockDataError("plays_observed.csv: duplicate play_id")
    return d


def _num(x, cast=float):
    return None if x in ("", None) else cast(x)


def wipe(conn) -> None:
    """Remove every mock row (keeps live/virtual data and the live chain)."""
    runs = [r["stats_run_id"] for r in conn.execute("SELECT stats_run_id FROM stats_runs WHERE period = 'mock_month'")]
    for t in ("play_weights", "shares", "flags", "stats_runs"):
        conn.execute(f"DELETE FROM {t} WHERE stats_run_id = ANY(%s)", (runs,))
    mock_plays = "SELECT play_id FROM plays WHERE chain = 'mock'"
    conn.execute(f"DELETE FROM play_weights WHERE play_id IN ({mock_plays})")
    conn.execute(f"DELETE FROM play_corrections WHERE play_id IN ({mock_plays})")
    conn.execute(f"DELETE FROM play_extents WHERE play_id IN ({mock_plays})")
    conn.execute("DELETE FROM plays WHERE chain = 'mock'")
    conn.execute("DELETE FROM owners WHERE song_id IN (SELECT song_id FROM songs WHERE source = 'mock')")
    conn.execute("DELETE FROM songs WHERE source = 'mock'")
    for t in ("mock_truth", "window_slots", "mock_meters"):
        conn.execute(f"DELETE FROM {t}")
    conn.execute("DELETE FROM meters WHERE source = 'mock'")
    conn.execute("DELETE FROM venues WHERE source = 'mock' AND venue_id NOT IN (SELECT venue_id FROM meters)")


def _copy(conn, sql: str, rows) -> None:
    with conn.cursor().copy(sql) as cp:
        for r in rows:
            cp.write_row(r)


def import_mock(conn, folder: Path = DEFAULT_DIR) -> dict:
    t0 = time.monotonic()
    d = read(folder)
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (chain.CHAIN_LOCK,))
        wipe(conn)
        for r in d["venues.csv"].itertuples(index=False):
            conn.execute("""INSERT INTO venues (venue_id, name, city, lat, lon, size_class, stratum, bars_in_stratum,
                                                open_hour, close_hour, source)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'mock')
                            ON CONFLICT (venue_id) DO UPDATE SET name = EXCLUDED.name, city = EXCLUDED.city,
                              lat = EXCLUDED.lat, lon = EXCLUDED.lon, size_class = EXCLUDED.size_class,
                              stratum = EXCLUDED.stratum, bars_in_stratum = EXCLUDED.bars_in_stratum,
                              open_hour = EXCLUDED.open_hour, close_hour = EXCLUDED.close_hour""",
                         (r.venue_id, r.name, r.city, _num(r.lat), _num(r.lon), r.size_class or None, r.stratum or None,
                          _num(r.bars_in_stratum, int), _num(r.open_hour, int), _num(r.close_hour, int)))
        m = d["meters.csv"]
        _copy(conn, "COPY mock_meters (meter_id, venue_id, catch_rate, installed_at) FROM STDIN",
              ((r.meter_id, r.venue_id, _num(r.catch_rate_true), r.installed_at or None) for r in m.itertuples(index=False)))
        clash = []
        for r in m.itertuples(index=False):
            got = conn.execute("""INSERT INTO meters (meter_id, venue_id, public_key_b64, catch_rate, source)
                                  VALUES (%s,%s,'',%s,'mock') ON CONFLICT (meter_id) DO NOTHING RETURNING meter_id""",
                               (r.meter_id, r.venue_id, _num(r.catch_rate_true))).fetchone()
            if got is None:
                clash.append(r.meter_id)
        sdf = d["songs_synthetic.csv"]
        existing = {r["song_id"] for r in conn.execute("SELECT song_id FROM songs WHERE song_id = ANY(%s)",
                                                         (list(sdf["song_id"]),))}   # catalogue songs: keep as they are
        _copy(conn, "COPY songs (song_id, title, artist_name, isrc, duration_s, status, source) FROM STDIN",
              ((r.song_id, r.title, r.artist_name, r.isrc or None, _num(r.duration_s), "ready", "mock")
               for r in sdf.itertuples(index=False) if r.song_id not in existing))
        _copy(conn, "COPY owners (song_id, owner_name, role, share_pct, momo) FROM STDIN",
              ((r.song_id, r.owner_name, r.role, _num(r.share_pct), r.momo or None)
               for r in d["owners_synthetic.csv"].itertuples(index=False) if r.song_id not in existing))

        po = d["plays_observed.csv"].copy()
        po["t"] = pd.to_datetime(po["started_at"], utc=True)
        po = po.sort_values(["t", "play_id"], kind="stable")
        prev = chain.GENESIS
        rows = []
        for r in po.itertuples(index=False):
            dur = float(r.duration_s)
            started = r.t.to_pydatetime()
            play = {"play_id": r.play_id, "meter_id": r.meter_id, "venue_id": r.venue_id, "song_id": r.song_id,
                    "started_at": started, "duration_s": round(dur, 1), "n_windows": max(1, math.ceil(dur / 10))}
            h = chain.link(prev, play)
            rows.append((r.play_id, r.meter_id, r.venue_id, r.song_id, started,
                         started + pd.Timedelta(seconds=dur).to_pytimedelta(), play["duration_s"], play["n_windows"],
                         _num(r.loudness_db), "mock", "mock", prev, h))
            prev = h
        _copy(conn, "COPY plays (play_id, meter_id, venue_id, song_id, started_at, ended_at, duration_s, n_windows, "
                    "loudness_db, source, chain, prev_chain_hash, chain_hash) FROM STDIN", rows)

        _copy(conn, "COPY window_slots (meter_id, slot_start, slot_minutes, windows_received, windows_expected, "
                    "mean_loudness_db) FROM STDIN",
              ((r.meter_id, r.slot_start, int(r.slot_minutes), int(r.windows_received), int(r.windows_expected),
                _num(r.mean_loudness_db)) for r in d["windows_observed.csv"].itertuples(index=False)))
        _copy(conn, "COPY mock_truth (true_play_id, venue_id, song_id, started_at, duration_s, scenario) FROM STDIN",
              ((r.true_play_id, r.venue_id, r.song_id, r.started_at, _num(r.duration_s), r.scenario)
               for r in d["plays_true.csv"].itertuples(index=False)))
    out = {"venues": len(d["venues.csv"]), "meters": len(m), "meters_kept_live": clash,
           "songs": len(sdf), "songs_from_catalogue": len(existing), "owners": len(d["owners_synthetic.csv"]), "plays": len(rows),
           "window_slots": len(d["windows_observed.csv"]), "true_plays": len(d["plays_true.csv"]),
           "chain_head": prev, "import_ms": int((time.monotonic() - t0) * 1000)}
    log.info("mock month imported: %s", out)
    return out


def main(argv=None) -> int:
    from server.stats.run import run_both
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", nargs="?", type=Path, default=DEFAULT_DIR)
    ap.add_argument("--no-stats", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    with connect(autocommit=True) as conn:
        out = import_mock(conn, a.folder)
        print({k: v for k, v in out.items() if k != "chain_head"})
        if out["meters_kept_live"]:
            print(f"note: meter ids {out['meters_kept_live']} are live/virtual meters: their rows were kept; the mock "
                  "plays still use their mock catch rate (mock_meters)")
        if not a.no_stats:
            r = run_both(conn, "mock_month")
            print(f"stats mock_month: {r['stats_run_id']} (raw {r['raw_stats_run_id']}), {r['n_plays']} plays, "
                  f"{r['n_songs']} songs, {r['n_flags']} flags, {r['duration_ms']} ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
