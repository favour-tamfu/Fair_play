"""Get the server demo-ready in one command (B-T16). Safe to run again and again (idempotent).

    python -m server.tools.demo_seed                 # check + fill what is missing
    python -m server.tools.demo_seed --reset-live    # also wipe the live test plays first (demo reset, D-017)
    python -m server.tools.demo_seed --reimport      # also regenerate + re-import the mock month

Steps:
  1. database migrations applied
  2. meters registered from contract/meters/*.pub.json, their venues known
  3. catalogue: the package songs (config.CATALOGUE_RANGE, S-000013…S-000195) ready and fingerprinted
  4. mock ownership: each catalogue song's artist as 100 % owner where no owner is set (D-015)
  5. mock month on the catalogue (D-014): generated + imported if missing (or --reimport)
  6. stats runs: live and mock_month, raw + standardised
  7. ledger audit intact
  8. the running api answers (and whether the dashboard pages are on)
Prints a checklist; exit code 1 if anything is not ready.
"""
from __future__ import annotations

import argparse
import sys

from server import config
from server.db import connect
from server.db.migrate import migrate

CATALOGUE = config.CATALOGUE_RANGE


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset-live", action="store_true", help="demo reset: wipe live test data first")
    ap.add_argument("--reimport", action="store_true", help="regenerate and re-import the mock month")
    ap.add_argument("--url", default="http://localhost:8000", help="the running api")
    a = ap.parse_args(argv)
    ok: dict[str, tuple[bool, str]] = {}

    applied = migrate()
    ok["migrations"] = (True, f"{len(applied)} applied now" if applied else "up to date")

    from server.ledger import audit
    from server.registry import fill_known_venues, load_meter_keys
    from server.stats.run import run_both
    from server.tools import catalogue_month, import_mock
    from server.tools.artist_owners import set_artist_owners
    with connect(autocommit=True) as c:
        if a.reset_live:
            from server.demo import reset_live
            r = reset_live(c, "demo_seed --reset-live")
            ok["demo reset"] = (True, f"epoch {r['epoch']}, {r['plays_removed']} live plays removed")

        with c.transaction():
            meters = load_meter_keys(c)
            fill_known_venues(c)
        live = c.execute("SELECT meter_id FROM meters WHERE source <> 'mock' ORDER BY 1").fetchall()
        ok["meters"] = ("M-07" in {m["meter_id"] for m in live},
                        f"{len(live)} live/virtual meters ({', '.join(m['meter_id'] for m in live)}); "
                        f"{len(meters)} key files loaded")

        s = c.execute("""SELECT count(*) AS n, count(*) FILTER (WHERE status = 'ready' AND n_hashes > 0) AS ready
                         FROM songs WHERE song_id BETWEEN %s AND %s""", CATALOGUE).fetchone()
        ok["catalogue"] = (s["n"] == config.CATALOGUE_SIZE and s["ready"] == config.CATALOGUE_SIZE,
                           f"{s['ready']}/{s['n']} songs ready and fingerprinted (expected {config.CATALOGUE_SIZE})")

        owners = set_artist_owners(c, *CATALOGUE)
        no_owner = c.execute("""SELECT count(*) AS n FROM songs s WHERE s.song_id BETWEEN %s AND %s
                                AND NOT EXISTS (SELECT 1 FROM owners o WHERE o.song_id = s.song_id)""", CATALOGUE).fetchone()["n"]
        ok["ownership"] = (no_owner == 0, f"{len(owners)} set now, {no_owner} songs without owner")

        mock = c.execute("""SELECT count(*) AS n, count(*) FILTER (WHERE song_id BETWEEN %s AND %s
                                                               OR song_id = ANY(%s)) AS cat
                            FROM plays WHERE chain = 'mock'""", (*CATALOGUE, list(catalogue_month.TEST_TRACK_IDS))).fetchone()
        if not ok["catalogue"][0]:
            note = "skipped: the catalogue is not ready (import the song package first)"
            mock = {"n": 0, "cat": 0}
        elif a.reimport or mock["n"] == 0 or mock["cat"] != mock["n"]:
            folder = catalogue_month.DEFAULT_OUT
            if a.reimport or not (folder / "plays_observed.csv").exists():
                catalogue_month.main(["--out", str(folder)])
            r = import_mock.import_mock(c, folder)
            mock = {"n": r["plays"], "cat": r["plays"]}
            note = f"imported now: {r['plays']} plays"
        else:
            note = f"{mock['n']} plays already loaded"
        ok["mock month"] = (mock["n"] > 0 and mock["cat"] == mock["n"], note + " (catalogue songs + 3 fictional test tracks)")

        runs = []
        for period in ("live", "mock_month"):
            runs.append(f"{period} {run_both(c, period)['stats_run_id']}")
        ok["stats"] = (True, "; ".join(runs))

        audit._cache.clear()
        st = audit.status(c)
        ok["ledger"] = (st["intact"], f"{'intact' if st['intact'] else 'BROKEN at ' + str(st['broken_at_play_id'])}, "
                                      f"{st['plays_checked']} plays checked")

    ok["admin token"] = (bool(config.ADMIN_TOKEN) and config.ADMIN_TOKEN != "change-me-too",
                         "set in .env (admin actions protected)" if config.ADMIN_TOKEN and config.ADMIN_TOKEN != "change-me-too"
                         else "NOT set: anyone on the network can reset or re-key meters (set ADMIN_TOKEN in .env)")
    import httpx
    try:
        h = httpx.get(a.url + "/health", timeout=5).json()
        page = httpx.get(a.url + "/", timeout=5).status_code
        ok["api"] = (bool(h.get("ok") and h.get("db")), f"{a.url} up, db reachable, server_time {h.get('server_time')}")
        ok["dashboard pages"] = (True, "served" if page == 200 else "OFF (SERVE_WEB=0 in .env; set 1 and restart api)")
    except httpx.HTTPError as e:
        ok["api"] = (False, f"{a.url} not reachable ({type(e).__name__}): docker compose up -d")
    width = max(map(len, ok))
    for k, (good, msg) in ok.items():
        print(f"  {'OK  ' if good else 'FAIL'}  {k:<{width}}  {msg}")
    return 0 if all(g for g, _ in ok.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
