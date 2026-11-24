"""Load a song package (catalogue.csv + audio/) into the song catalogue, like 60 uploads in one go.

    python -m server.tools.import_catalogue PATH/TO/Fair_Play_song_package [--dry-run]

Per row of catalogue.csv: the audio file is checked against sha256_tagged, copied to media/songs/S-xxxxxx.mp3,
a songs row is written (source 'upload', status 'uploaded') and a fingerprint job is queued — the same path as
POST /api/v1/songs, so the fingerprint worker indexes the songs and runs its duplicate check.
Owners are copied only when the package has them (today it has none: payouts for those songs stay pending).
Re-running is safe: a row whose title + artist is already in the catalogue is skipped.
Writes song_map.csv (package song_id -> server song_id) into the package folder.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from pathlib import Path

from server import config
from server.api.songs import stored_path
from server.db import connect, jobs


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        while b := f.read(1 << 20):
            h.update(b)
    return h.hexdigest()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("package", type=Path)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    rows = list(csv.DictReader(open(a.package / "catalogue.csv", encoding="utf-8-sig")))
    bad = [r["song_id"] for r in rows if sha256(a.package / r["audio_file"]) != r["sha256_tagged"]]
    if bad:
        print("hash mismatch, nothing imported:", bad)
        return 1
    mapping, added = [], 0
    with connect(autocommit=True) as conn:
        for r in rows:
            got = conn.execute("SELECT song_id FROM songs WHERE title = %s AND artist_name = %s",
                               (r["title"], r["artist_name"])).fetchone()
            if got:
                mapping.append((r["song_id"], got["song_id"], "already in catalogue"))
                continue
            if a.dry_run:
                mapping.append((r["song_id"], "", "would import"))
                continue
            with conn.transaction():
                sid = f"S-{conn.execute('SELECT nextval(%s) AS n', ('song_upload_seq',)).fetchone()['n']:06d}"
                src = a.package / r["audio_file"]
                dest = config.SONGS_DIR / f"{sid}{src.suffix.lower()}"
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, dest)
                conn.execute("""INSERT INTO songs (song_id, title, artist_name, isrc, iswc, duration_s, status, file_path, source)
                                VALUES (%s, %s, %s, %s, %s, %s, 'uploaded', %s, 'upload')""",
                             (sid, r["title"], r["artist_name"], r["isrc"] or None, r["iswc"] or None,
                              float(r["duration_s"]) if r["duration_s"] else None, stored_path(dest)))
                for o in json.loads(r["owners"]) if r["owners"].strip().startswith("[") else []:
                    conn.execute("INSERT INTO owners (song_id, owner_name, role, share_pct, momo) VALUES (%s,%s,%s,%s,%s)",
                                 (sid, o["name"], o["role"], o["share_pct"], o.get("momo")))
                jobs.enqueue(conn, "fingerprint", sid)
            mapping.append((r["song_id"], sid, "imported"))
            added += 1
    if not a.dry_run:
        with open(a.package / "song_map.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["package_song_id", "server_song_id", "result"])
            w.writerows(mapping)
    print(f"{added} imported, {len(rows) - added} skipped or dry-run")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
