"""Landmark hashes and window matching — brief §5.2 and §5.3 (fp-1.0).

Peaks → hashes:
    for each anchor peak (t1, f1) in time order, candidate targets are peaks with 1 ≤ t2−t1 ≤ DT_MAX and
    |f2−f1| ≤ DF_MAX, sorted by (t2−t1, |f2−f1|, f2) — f2 is our deterministic tie-break — first FANOUT kept.
    hash = (f1 << 13) | ((f2 − f1 + 64) << 6) | (t2 − t1)   → 21-bit int, emitted with t1.

Window → match:
    every window hash votes for (song, t_song − t_window); score = votes at offset ±1 frame;
    accept if best ≥ MATCH_MIN_ALIGNED and best ≥ MATCH_RATIO × max(best score of any other song, 1).

Peaks can be any structured array with "frame" and "bin" fields (peaks.extract_peaks output or
schema.decode_peak_records output), or an (N, 2) integer array of (frame, bin).
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Iterable, Optional, Protocol, Sequence

import numpy as np

from .constants import DF_MAX, DT_MAX, DT_MIN, FANOUT, FRAME_S, MATCH_MIN_ALIGNED, MATCH_RATIO

HASH_DTYPE = np.dtype([("hash", "<u4"), ("t", "<i4")])
HASH_BITS = 21
_CHUNK = 4096  # anchors processed per vectorised chunk (bounds memory on long songs)


# --------------------------------------------------------------------------- peaks → hashes

def _frames_bins(peaks) -> tuple[np.ndarray, np.ndarray]:
    """Return (frames, bins) as int64 arrays sorted by (frame, bin)."""
    arr = np.asarray(peaks)
    if arr.dtype.names:
        frames = arr["frame"].astype(np.int64)
        bins = arr["bin"].astype(np.int64)
    elif arr.size == 0:
        return np.empty(0, np.int64), np.empty(0, np.int64)
    else:
        arr = arr.reshape(-1, 2).astype(np.int64)
        frames, bins = arr[:, 0], arr[:, 1]
    order = np.lexsort((bins, frames))
    return frames[order], bins[order]


def make_hashes(peaks) -> np.ndarray:
    """Landmark hashes of a peak list. Returns a HASH_DTYPE array (hash uint32, t int32) in anchor order."""
    frames, bins = _frames_bins(peaks)
    n = len(frames)
    if n < 2:
        return np.empty(0, HASH_DTYPE)

    # candidate targets of anchor i are the contiguous index range [lo[i], hi[i]) (frames sorted)
    lo = np.searchsorted(frames, frames + DT_MIN, side="left")
    hi = np.searchsorted(frames, frames + DT_MAX, side="right")
    width = int((hi - lo).max(initial=0))
    if width == 0:
        return np.empty(0, HASH_DTYPE)

    out_h, out_t = [], []
    cols = np.arange(width)
    for s in range(0, n, _CHUNK):
        a = np.arange(s, min(s + _CHUNK, n))
        idx = lo[a, None] + cols[None, :]                 # (chunk, width)
        valid = idx < hi[a, None]
        idx = np.where(valid, idx, 0)
        dt = frames[idx] - frames[a, None]
        df = bins[idx] - bins[a, None]
        valid &= np.abs(df) <= DF_MAX
        # sort key (dt, |df|, f2) packed into one int; invalid → +inf-like
        key = (dt << 20) | (np.abs(df) << 10) | bins[idx]
        key = np.where(valid, key, np.iinfo(np.int64).max)
        k = min(FANOUT, width)
        pick = np.argsort(key, axis=1, kind="stable")[:, :k]
        rows = np.arange(len(a))[:, None]
        ok = valid[rows, pick]
        dt_p, df_p = dt[rows, pick], df[rows, pick]
        f1 = np.broadcast_to(bins[a, None], pick.shape)
        t1 = np.broadcast_to(frames[a, None], pick.shape)
        h = (f1 << 13) | ((df_p + 64) << 6) | dt_p
        out_h.append(h[ok])                               # row-major → anchor order, then candidate order
        out_t.append(t1[ok])

    res = np.empty(sum(len(x) for x in out_h), HASH_DTYPE)
    res["hash"] = np.concatenate(out_h)
    res["t"] = np.concatenate(out_t)
    return res


def slice_peaks(peaks, start_frame: int, n_frames: int) -> np.ndarray:
    """Peaks with start_frame ≤ frame < start_frame+n_frames, frames re-based to 0 (e.g. cut a 10 s window
    out of a whole song for the duplicate check or the evaluation harness). Returns (N, 2) int64 (frame, bin)."""
    frames, bins = _frames_bins(peaks)
    m = (frames >= start_frame) & (frames < start_frame + n_frames)
    return np.stack([frames[m] - start_frame, bins[m]], axis=1)


# --------------------------------------------------------------------------- index

class HashIndex(Protocol):
    """Anything that maps a hash to its (song_id, t_in_song) occurrences (MemoryIndex here, DbIndex on B)."""

    def lookup(self, h: int) -> Sequence[tuple[str, int]]: ...


class MemoryIndex:
    """In-memory hash → [(song_id, t)] index."""

    def __init__(self) -> None:
        self._d: dict[int, list[tuple[str, int]]] = defaultdict(list)
        self.songs: dict[str, int] = {}  # song_id → number of hashes

    def add(self, song_id: str, hashes: np.ndarray) -> None:
        if song_id in self.songs:
            raise ValueError(f"song {song_id} already indexed")
        d = self._d
        for h, t in zip(hashes["hash"].tolist(), hashes["t"].tolist()):
            d[h].append((song_id, t))
        self.songs[song_id] = len(hashes)

    def add_peaks(self, song_id: str, peaks) -> int:
        hashes = make_hashes(peaks)
        self.add(song_id, hashes)
        return len(hashes)

    def lookup(self, h: int) -> Sequence[tuple[str, int]]:
        return self._d.get(h, ())

    def __len__(self) -> int:
        return sum(self.songs.values())


# --------------------------------------------------------------------------- matching

@dataclass(frozen=True)
class MatchResult:
    song_id: Optional[str]      # best candidate (also when rejected — stored for evaluation); None if no votes
    offset_frames: int          # song frame where the window starts
    best_score: int
    second_score: int           # best score of any other song
    confidence: float           # best_score / number of window hashes
    accepted: bool
    n_hashes: int

    @property
    def offset_s(self) -> float:
        return self.offset_frames * FRAME_S


def match_window(window_hashes, index: HashIndex) -> MatchResult:
    """Match one window's hashes (HASH_DTYPE array, or iterable of (hash, t)) against an index."""
    if isinstance(window_hashes, np.ndarray) and window_hashes.dtype.names:
        pairs: Iterable = zip(window_hashes["hash"].tolist(), window_hashes["t"].tolist())
        n = len(window_hashes)
    else:
        window_hashes = list(window_hashes)
        pairs, n = window_hashes, len(window_hashes)

    votes: Counter = Counter()
    for h, tq in pairs:
        for song_id, ts in index.lookup(int(h)):
            votes[(song_id, ts - int(tq))] += 1

    if not votes:
        return MatchResult(None, 0, 0, 0, 0.0, False, n)

    # ±1 frame tolerance; the best 3-wide sum can sit on an offset with no votes of its own, so test neighbours too
    candidates = {(s, o + d) for (s, o) in votes for d in (-1, 0, 1)}
    # sort key (ascending = better): score desc, centre votes desc, offset asc, song_id asc → deterministic
    best_per_song: dict[str, tuple[int, int, int, str]] = {}
    for s, o in candidates:
        score = votes.get((s, o - 1), 0) + votes.get((s, o), 0) + votes.get((s, o + 1), 0)
        key = (-score, -votes.get((s, o), 0), o, s)
        if s not in best_per_song or key < best_per_song[s]:
            best_per_song[s] = key

    ordered = sorted(best_per_song.values())
    neg_best, _, best_off, best_song = ordered[0]
    best_score = -neg_best
    second = -ordered[1][0] if len(ordered) > 1 else 0
    accepted = best_score >= MATCH_MIN_ALIGNED and best_score >= MATCH_RATIO * max(second, 1)
    return MatchResult(best_song, best_off, best_score, second, best_score / max(n, 1), accepted, n)


__all__ = ["make_hashes", "slice_peaks", "MemoryIndex", "HashIndex", "MatchResult", "match_window", "HASH_DTYPE"]
