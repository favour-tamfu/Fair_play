"""Tests for fairplay_core.landmarks (B-T01). Synthetic peaks only (no dependency on peaks.py)."""
import time

import numpy as np
import pytest

from fairplay_core.constants import BIN_MAX, BIN_MIN, FRAMES_PER_WINDOW
from fairplay_core.landmarks import (
    HASH_DTYPE, MemoryIndex, make_hashes, match_window, slice_peaks,
)


def H(f1, f2, dt):
    return (f1 << 13) | ((f2 - f1 + 64) << 6) | dt


def reference_hashes(peaks):
    """Plain-loop transcription of brief §5.2 (tie-break f2 ascending) to check the vectorised version."""
    p = sorted((int(f), int(b)) for f, b in peaks)
    out = []
    for t1, f1 in p:
        cands = [(t2 - t1, abs(f2 - f1), f2) for t2, f2 in p if 1 <= t2 - t1 <= 63 and abs(f2 - f1) <= 63]
        for dt, _, f2 in sorted(cands)[:5]:
            out.append((H(f1, f2, dt), t1))
    return out


def random_song(rng, n_frames, per_block=30, block=32):
    """~30 peaks per 32-frame block, like the density cap of the real extractor."""
    peaks = []
    for b0 in range(0, n_frames, block):
        nb = min(block, n_frames - b0)
        k = per_block if nb == block else max(1, per_block * nb // block)
        frames = rng.integers(b0, b0 + nb, size=k)
        bins = rng.integers(BIN_MIN, BIN_MAX + 1, size=k)
        peaks += list(zip(frames.tolist(), bins.tolist()))
    return np.unique(np.array(peaks, dtype=np.int64), axis=0)


def as_list(h):
    return list(zip(h["hash"].tolist(), h["t"].tolist()))


# ------------------------------------------------------------------ make_hashes

def test_hand_made_hashes():
    peaks = [(0, 100), (1, 110), (2, 90), (70, 100)]
    # anchor (0,100): (1,110) dt1 df+10 ; (2,90) dt2 df-10 ; (70,100) dt70 too far
    # anchor (1,110): (2,90) dt1 df-20 ; anchors (2,90),(70,100): nothing within 63 frames
    assert as_list(make_hashes(peaks)) == [(823937, 0), (822658, 0), (903937, 1)]
    assert H(100, 110, 1) == 823937 and H(100, 90, 2) == 822658 and H(110, 90, 1) == 903937


def test_fanout_and_candidate_order():
    anchor = (0, 100)
    targets = [(1, 130), (1, 90), (1, 110), (2, 100), (3, 101), (3, 99), (5, 100), (9, 100)]
    got = as_list(make_hashes([anchor] + targets))
    first = [h for h, t in got if t == 0]
    # order by (dt, |df|, f2): (1,110)|10, (1,90)|10 → tie → f2 90 first ; then (1,130)|30 ; (2,100) ; (3,99),(3,101) tie → 99
    assert first == [H(100, 90, 1), H(100, 110, 1), H(100, 130, 1), H(100, 100, 2), H(100, 99, 3)]


@pytest.mark.parametrize("target, n", [
    ((1, 163), 1), ((1, 164), 0),   # df +63 ok, +64 too far
    ((1, 37), 1), ((1, 36), 0),     # df -63 ok, -64 too far
    ((0, 120), 0),                  # same frame never pairs
])
def test_df_limits_and_same_frame(target, n):
    assert len(make_hashes([(0, 100), target])) == n


def test_dt_63_included_dt_64_excluded():
    assert as_list(make_hashes([(0, 100), (63, 100)])) == [(H(100, 100, 63), 0)]
    assert len(make_hashes([(0, 100), (64, 100)])) == 0


def test_matches_reference_on_random_peaks():
    rng = np.random.default_rng(7)
    p = random_song(rng, 600)
    assert as_list(make_hashes(p)) == reference_hashes(p)


def test_input_order_and_format_do_not_matter():
    rng = np.random.default_rng(3)
    p = random_song(rng, 400)
    shuffled = p[rng.permutation(len(p))]
    structured = np.zeros(len(p), dtype=[("frame", "<i4"), ("bin", "<i2"), ("mag_db", "<f4")])
    structured["frame"], structured["bin"] = p[:, 0], p[:, 1]
    a = make_hashes(p)
    assert np.array_equal(a, make_hashes(shuffled))
    assert np.array_equal(a, make_hashes(structured))


def test_hash_fits_21_bits_and_dtype():
    h = make_hashes(random_song(np.random.default_rng(1), 2000))
    assert h.dtype == HASH_DTYPE
    assert int(h["hash"].max()) < 2 ** 21
    assert np.all(np.diff(h["t"]) >= 0)  # anchor (time) order


@pytest.mark.parametrize("peaks", [[], [(5, 100)], np.empty((0, 2), dtype=np.int64)])
def test_degenerate_inputs(peaks):
    assert len(make_hashes(peaks)) == 0


def test_whole_song_speed():
    p = random_song(np.random.default_rng(0), 9400)  # ~5 min song
    t0 = time.perf_counter()
    h = make_hashes(p)
    dt = time.perf_counter() - t0
    print(f"\nmake_hashes: {len(p)} peaks -> {len(h)} hashes in {dt * 1000:.0f} ms")
    assert dt < 5.0


def test_slice_peaks_rebases_frames():
    p = np.array([[5, 50], [100, 60], [200, 70], [410, 80], [411, 90]])
    s = slice_peaks(p, 100, 311)
    assert s.tolist() == [[0, 60], [100, 70], [310, 80]]


# ------------------------------------------------------------------ matching

@pytest.fixture(scope="module")
def catalogue():
    rng = np.random.default_rng(42)
    songs = {f"S-00000{i}": random_song(rng, 3000) for i in (1, 2, 3)}  # ~96 s each
    idx = MemoryIndex()
    for sid, p in songs.items():
        idx.add_peaks(sid, p)
    return songs, idx


def noisy_window(rng, song_peaks, offset, drop=0.3, extra=0.2, jitter=0.0):
    w = slice_peaks(song_peaks, offset, FRAMES_PER_WINDOW)
    w = w[rng.random(len(w)) >= drop]                        # lose 30% of the peaks
    if jitter:
        j = rng.random(len(w)) < jitter
        w[j, 0] = np.clip(w[j, 0] + rng.choice([-1, 1], j.sum()), 0, FRAMES_PER_WINDOW - 1)
    n_extra = int(extra * len(w))                            # add 20% random peaks
    junk = np.stack([rng.integers(0, FRAMES_PER_WINDOW, n_extra), rng.integers(BIN_MIN, BIN_MAX + 1, n_extra)], 1)
    return np.unique(np.concatenate([w, junk]), axis=0)


def test_noisy_slice_matches_correct_song_and_offset(catalogue):
    songs, idx = catalogue
    rng = np.random.default_rng(100)
    r = match_window(make_hashes(noisy_window(rng, songs["S-000002"], 100)), idx)
    assert r.accepted, r
    assert r.song_id == "S-000002"
    assert abs(r.offset_frames - 100) <= 1
    assert abs(r.offset_s - 3.2) <= 0.032
    assert r.best_score >= 2 * max(r.second_score, 1)
    assert 0 < r.confidence <= 1


@pytest.mark.parametrize("seed", range(10))
def test_noisy_slices_many(catalogue, seed):
    songs, idx = catalogue
    rng = np.random.default_rng(1000 + seed)
    sid = f"S-00000{1 + seed % 3}"
    off = int(rng.integers(0, 3000 - FRAMES_PER_WINDOW))
    r = match_window(make_hashes(noisy_window(rng, songs[sid], off, jitter=0.2)), idx)
    assert r.accepted and r.song_id == sid and abs(r.offset_frames - off) <= 1, r


@pytest.mark.parametrize("seed", range(10))
def test_random_query_not_accepted(catalogue, seed):
    _, idx = catalogue
    rng = np.random.default_rng(5000 + seed)
    r = match_window(make_hashes(random_song(rng, FRAMES_PER_WINDOW)), idx)
    assert not r.accepted, r


def test_empty_window_not_accepted(catalogue):
    _, idx = catalogue
    r = match_window(make_hashes([]), idx)
    assert (r.song_id, r.accepted, r.n_hashes, r.confidence) == (None, False, 0, 0.0)


def test_tolerance_uses_neighbour_offsets():
    """Votes split across offsets 9 and 11 (none at 10) must still score 8 at offset 10."""
    class Idx:
        def lookup(self, h):
            return [("S-000001", 9 + h % 2 * 2)]           # hash parity → offset 9 or 11
    r = match_window([(h, 0) for h in range(8)], Idx())
    assert r.accepted and r.offset_frames == 10 and r.best_score == 8


def test_ratio_rule_rejects_ambiguous():
    class Idx:
        def lookup(self, h):
            return [("S-000001", 50), ("S-000002", 70)] if h < 6 else [("S-000001", 50)]
    r = match_window([(h, 0) for h in range(10)], Idx())  # song1: 10 votes, song2: 6 → 10 < 2×6
    assert r.song_id == "S-000001" and r.best_score == 10 and r.second_score == 6 and not r.accepted


def test_min_aligned_rule():
    class Idx:
        def lookup(self, h):
            return [("S-000001", 5)]
    assert not match_window([(h, 0) for h in range(7)], Idx()).accepted
    assert match_window([(h, 0) for h in range(8)], Idx()).accepted


def test_duplicate_song_id_rejected():
    idx = MemoryIndex()
    idx.add_peaks("S-000001", [(0, 100), (1, 110)])
    with pytest.raises(ValueError):
        idx.add_peaks("S-000001", [(0, 100), (1, 110)])
