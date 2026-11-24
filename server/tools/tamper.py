"""DEMO ONLY: tamper with one play directly in Postgres (bypassing the app) to show the ledger catching it.

    python -m server.tools.tamper --latest                 # change the newest play's song (gives it to another song)
    python -m server.tools.tamper --play-id P-3f2a9c1b7d4e
    python -m server.tools.tamper --restore                # put every tampered play back exactly as it was

The original values are saved to server/anchors/tamper_backup.json (gitignored) before the change.
Expected: GET /api/v1/ledger/status → intact=false, broken_at_play_id = that play; the scheduler announces a
`ledger` event within ~2 s (dashboard red banner) and payouts are frozen until --restore.
"""
from __future__ import annotations

import argparse
import json
import sys

from server import config
from server.db import connect

BACKUP = config.ANCHORS_DIR / "tamper_backup.json"


def _load() -> list[dict]:
    return json.loads(BACKUP.read_text(encoding="utf-8")) if BACKUP.exists() else []


def tamper(play_id: str | None, latest: bool) -> int:
    with connect(autocommit=True) as conn, conn.transaction():
        if latest:
            p = conn.execute("SELECT play_id, song_id FROM plays WHERE chain = 'live' ORDER BY seq_no DESC LIMIT 1").fetchone()
        else:
            p = conn.execute("SELECT play_id, song_id FROM plays WHERE play_id = %s", (play_id,)).fetchone()
        if p is None:
            print("no such play")
            return 1
        other = conn.execute("SELECT song_id, title FROM songs WHERE song_id <> %s AND status = 'ready' "
                             "ORDER BY song_id LIMIT 1", (p["song_id"],)).fetchone()
        new_song = other["song_id"] if other else "S-999999"
        backup = [b for b in _load() if b["play_id"] != p["play_id"]] + [{"play_id": p["play_id"], "song_id": p["song_id"]}]
        BACKUP.parent.mkdir(parents=True, exist_ok=True)
        BACKUP.write_text(json.dumps(backup, indent=2), encoding="utf-8")
        conn.execute("UPDATE plays SET song_id = %s WHERE play_id = %s", (new_song, p["play_id"]))
    print(f"TAMPERED {p['play_id']}: song_id {p['song_id']} -> {new_song} (direct SQL, no new hash). "
          f"Restore with: python -m server.tools.tamper --restore")
    return 0


def restore() -> int:
    items = _load()
    if not items:
        print("nothing to restore")
        return 0
    with connect(autocommit=True) as conn, conn.transaction():
        for b in items:
            conn.execute("UPDATE plays SET song_id = %s WHERE play_id = %s", (b["song_id"], b["play_id"]))
            print(f"restored {b['play_id']}: song_id -> {b['song_id']}")
    BACKUP.unlink()
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--play-id")
    g.add_argument("--latest", action="store_true")
    g.add_argument("--restore", action="store_true")
    a = ap.parse_args(argv)
    return restore() if a.restore else tamper(a.play_id, a.latest)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
