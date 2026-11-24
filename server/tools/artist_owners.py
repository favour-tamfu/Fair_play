"""Mock ownership (D-015): register each song's artist as its 100 % owner, for songs that have no owners yet.

    python -m server.tools.artist_owners [--songs S-000013..S-000072]

Prototype only: the real singer / composer / producer splits are not known yet. Songs that already have owners
(e.g. uploaded through the portal with their splits) are never changed. No MoMo number is invented (left empty).
"""
from __future__ import annotations

import argparse

from server.db import connect


def set_artist_owners(conn, lo: str, hi: str) -> list[str]:
    with conn.transaction():
        rows = conn.execute("""SELECT s.song_id, s.artist_name FROM songs s
                               WHERE s.song_id BETWEEN %s AND %s AND s.artist_name IS NOT NULL
                                 AND NOT EXISTS (SELECT 1 FROM owners o WHERE o.song_id = s.song_id)
                               ORDER BY s.song_id""", (lo, hi)).fetchall()
        for r in rows:
            conn.execute("INSERT INTO owners (song_id, owner_name, role, share_pct, momo) VALUES (%s, %s, 'singer', 100, NULL)",
                         (r["song_id"], r["artist_name"]))
    return [r["song_id"] for r in rows]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--songs", default="S-000013..S-000072", help="song_id range lo..hi")
    a = ap.parse_args(argv)
    lo, hi = a.songs.split("..")
    with connect(autocommit=True) as conn:
        done = set_artist_owners(conn, lo, hi)
    print(f"{len(done)} songs: artist registered as 100 % owner" + (f" ({done[0]} to {done[-1]})" if done else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
