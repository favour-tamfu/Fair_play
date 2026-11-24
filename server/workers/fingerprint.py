"""Fingerprint worker (B-T04, "the cataloguer"): uploaded song → hashes in the index, with a duplicate check.

Job "fingerprint", ref = song_id (or "song_id:approved" / "song_id:reindex" to skip the duplicate check).
  1. status → processing (the portal shows it)
  2. decode to 8 kHz mono (ffmpeg) → extract_peaks over the whole track → make_hashes, on every grid phase in
     config.FP_INDEX_SHIFTS (0 and half a hop: meter windows never line up with one grid — D-006)
  3. duplicate check (brief §5.4): 10 s slices at 20/50/80 % matched against the CURRENT index; ≥2 slices on the
     same existing song → status duplicate_suspected, duplicate_of, flag row; not indexed until an admin approves
  4. replace the song's rows in fp_hashes (COPY), n_hashes, measured duration_s, status → ready
On any error: status → failed (the job is marked error by the job loop).
"""
from __future__ import annotations

import logging
from collections import Counter
from typing import Optional

import numpy as np
import psycopg

from fairplay_core.constants import SAMPLE_RATE, WINDOW_SAMPLES
from fairplay_core.landmarks import make_hashes, match_window
from fairplay_core.peaks import extract_peaks
from fairplay_core.schema import format_utc
from server import config
from server.api.songs import resolve_path
from server.db import notify
from server.fp.audio import decode_8k
from server.fp.index import DbIndex

log = logging.getLogger("fingerprint")
INDEX = DbIndex()   # this worker's copy of the index (used for the duplicate check)


def song_hashes(x8: np.ndarray, peaks0: Optional[np.ndarray] = None) -> np.ndarray:
    """Hashes of the whole song on every grid phase in config.FP_INDEX_SHIFTS (catalogue side only, D-006)."""
    parts = []
    for shift in config.FP_INDEX_SHIFTS:
        p = peaks0 if (shift == 0 and peaks0 is not None) else extract_peaks(x8[shift:])
        parts.append(make_hashes(p))
    return np.concatenate(parts) if len(parts) > 1 else parts[0]


def find_duplicate(x8, index: DbIndex) -> Optional[tuple[str, int]]:
    """Return (song_id, n_slices_matched) if ≥ DUP_MIN_HITS slices of x8 match the same indexed song."""
    if len(x8) < WINDOW_SAMPLES:
        return None
    hits: Counter = Counter()
    for frac in config.DUP_SLICES:
        start = min(int(frac * len(x8)), len(x8) - WINDOW_SAMPLES)
        r = match_window(make_hashes(extract_peaks(x8[start:start + WINDOW_SAMPLES])), index)
        if r.accepted:
            hits[r.song_id] += 1
    if hits:
        song, n = hits.most_common(1)[0]
        if n >= config.DUP_MIN_HITS:
            return song, n
    return None


def process(conn: psycopg.Connection, ref: str, index: DbIndex = INDEX) -> str:
    """Fingerprint one song. Returns the final status. `conn` must be autocommit."""
    song_id, _, mode = ref.partition(":")
    with conn.transaction():
        song = conn.execute("SELECT * FROM songs WHERE song_id = %s FOR UPDATE", (song_id,)).fetchone()
        if song is None:
            raise ValueError(f"unknown song {song_id}")
        conn.execute("UPDATE songs SET status = 'processing' WHERE song_id = %s", (song_id,))
    try:
        x8 = decode_8k(resolve_path(song["file_path"]))
        duration = len(x8) / SAMPLE_RATE
        peaks = extract_peaks(x8)
        hashes = song_hashes(x8, peaks)

        if mode not in ("approved", "reindex"):
            index.sync(conn)
            dup = find_duplicate(x8, index)
            if dup:
                with conn.transaction():
                    conn.execute("UPDATE songs SET status = 'duplicate_suspected', duplicate_of = %s, duration_s = %s "
                                 "WHERE song_id = %s", (dup[0], duration, song_id))
                    f = conn.execute("""INSERT INTO flags (type, song_id, detail) VALUES ('duplicate_suspected', %s, %s)
                                        RETURNING flag_id, type, song_id, venue_id, detail, created_at""",
                                     (song_id, f"upload matches {dup[0]} in {dup[1]}/{len(config.DUP_SLICES)} slices")
                                     ).fetchone()
                    notify(conn, "flag", {**f, "created_at": format_utc(f["created_at"])})
                log.info("%s looks like a duplicate of %s (%d slices)", song_id, dup[0], dup[1])
                return "duplicate_suspected"

        with conn.transaction():
            conn.execute("DELETE FROM fp_hashes WHERE song_id = %s", (song_id,))
            with conn.cursor().copy("COPY fp_hashes (hash, song_id, t) FROM STDIN") as cp:
                for h, t in zip(hashes["hash"].tolist(), hashes["t"].tolist()):
                    cp.write_row((h, song_id, t))
            conn.execute("UPDATE songs SET status = 'ready', n_hashes = %s, duration_s = %s, duplicate_of = NULL "
                         "WHERE song_id = %s", (len(hashes), duration, song_id))
        log.info("%s ready: %.1f s, %d peaks, %d hashes", song_id, duration, len(peaks), len(hashes))
        return "ready"
    except Exception:
        with conn.transaction():
            conn.execute("UPDATE songs SET status = 'failed' WHERE song_id = %s", (song_id,))
        raise


def handle(conn: psycopg.Connection, job: dict) -> None:
    process(conn, job["ref"])


if __name__ == "__main__":
    from server.workers.base import run_jobs
    run_jobs("fingerprint", "fingerprint", handle)
