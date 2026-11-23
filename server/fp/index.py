"""DbIndex: the fingerprint index (hash → [(song_id, t)]) held in memory, loaded from the fp_hashes table.

Same `lookup()` interface as core.landmarks.MemoryIndex, so `match_window` works with either.
`sync(conn)` is cheap (one small query) and loads/unloads songs whose ready-state changed — call it before matching.
Fast enough for the demo scale (≤ 300 songs); the full index is a few hundred thousand entries.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Sequence

import psycopg

log = logging.getLogger(__name__)


class DbIndex:
    def __init__(self) -> None:
        self._d: dict[int, list[tuple[str, int]]] = defaultdict(list)
        self.songs: dict[str, int] = {}          # song_id → n_hashes loaded

    def lookup(self, h: int) -> Sequence[tuple[str, int]]:
        return self._d.get(h, ())

    def __len__(self) -> int:
        return sum(self.songs.values())

    def sync(self, conn: psycopg.Connection) -> tuple[list[str], list[str]]:
        """Bring the index in line with songs.status='ready'. Returns (added, removed) song ids."""
        ready = {r["song_id"]: r["n_hashes"] for r in
                 conn.execute("SELECT song_id, n_hashes FROM songs WHERE status = 'ready'")}
        removed = [s for s in self.songs if s not in ready or ready[s] != self.songs[s]]
        added = [s for s in ready if s not in self.songs or s in removed]
        if removed:
            self._remove(removed)
        for song_id in added:
            rows = conn.execute("SELECT hash, t FROM fp_hashes WHERE song_id = %s", (song_id,)).fetchall()
            for r in rows:
                self._d[r["hash"]].append((song_id, r["t"]))
            self.songs[song_id] = len(rows)
        if added or removed:
            log.info("index sync: +%d −%d songs, %d hashes total", len(added), len(removed), len(self))
        return added, removed

    def _remove(self, song_ids: list[str]) -> None:
        gone = set(song_ids)
        for h in list(self._d):
            kept = [e for e in self._d[h] if e[0] not in gone]
            if kept:
                self._d[h] = kept
            else:
                del self._d[h]
        for s in song_ids:
            self.songs.pop(s, None)
