"""Remove songs from the catalogue for good (test uploads, songs that must not appear in a demo).

    python -m server.tools.retire_songs S-000001..S-000012 [--dry-run]

Plays of these songs are part of the hash-chained play log, so they cannot be deleted one by one without
breaking it. If any LIVE play uses one of the songs, the tool first runs the demo reset (new live-chain epoch,
recorded in the anchors file, D-017), which removes all live test plays. Songs used by the mock month are refused.
Then removed: songs, fingerprints, owners, their flags and stored shares, fingerprint jobs, and the audio files.
The matcher drops the songs from its index on its next sync.
"""
from __future__ import annotations

import argparse
import sys

from server import config
from server.api.songs import resolve_path
from server.db import connect


def expand(spec: str) -> list[str]:
    if ".." in spec:
        lo, hi = spec.split("..")
        return [f"S-{n:06d}" for n in range(int(lo[2:]), int(hi[2:]) + 1)]
    return [s.strip() for s in spec.split(",") if s.strip()]


def retire(conn, ids: list[str], dry_run: bool = False) -> dict:
    songs = conn.execute("SELECT song_id, title, file_path FROM songs WHERE song_id = ANY(%s) ORDER BY song_id",
                         (ids,)).fetchall()
    found = [s["song_id"] for s in songs]
    mock = conn.execute("SELECT count(*) AS n FROM plays WHERE chain = 'mock' AND song_id = ANY(%s)", (found,)).fetchone()["n"]
    if mock:
        raise SystemExit(f"refused: {mock} mock-month plays use these songs (rebuild the mock month without them first)")
    live = conn.execute("SELECT count(*) AS n FROM plays WHERE chain = 'live' AND song_id = ANY(%s)", (found,)).fetchone()["n"]
    out = {"songs": [f"{s['song_id']} {s['title']}" for s in songs], "live_plays": live, "reset": None}
    if dry_run:
        return out
    if live:
        from server.demo import reset_live
        out["reset"] = reset_live(conn, f"retire songs {found[0]}..{found[-1]}")
    with conn.transaction():
        for t in ("fp_hashes", "owners", "flags", "shares"):
            conn.execute(f"DELETE FROM {t} WHERE song_id = ANY(%s)", (found,))
        conn.execute("DELETE FROM jobs WHERE kind = 'fingerprint' AND split_part(ref, ':', 1) = ANY(%s)", (found,))
        conn.execute("UPDATE songs SET duplicate_of = NULL WHERE duplicate_of = ANY(%s)", (found,))
        conn.execute("DELETE FROM songs WHERE song_id = ANY(%s)", (found,))
    removed = 0
    for s in songs:
        if s["file_path"]:
            p = resolve_path(s["file_path"])
            if p.is_file() and config.SONGS_DIR in p.resolve().parents:
                p.unlink()
                removed += 1
    out["files_removed"] = removed
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("songs", help="S-000001..S-000012 or S-000001,S-000004")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    with connect(autocommit=True) as conn:
        out = retire(conn, expand(a.songs), a.dry_run)
    print(("DRY RUN, nothing changed\n" if a.dry_run else "") + "\n".join("  " + s for s in out["songs"]))
    print(f"live plays using them: {out['live_plays']}"
          + (f"; demo reset done (epoch {out['reset']['epoch']}, {out['reset']['plays_removed']} live plays removed)"
             if out.get("reset") else ""))
    if not a.dry_run:
        print(f"removed {len(out['songs'])} songs, {out['files_removed']} audio files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
