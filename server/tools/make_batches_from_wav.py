"""Cut a WAV into signed meter batches — exactly what Laptop A's meter computes, without a microphone.

    python -m server.tools.make_batches_from_wav data\\song.wav --post http://localhost:8000
    python -m server.tools.make_batches_from_wav data\\song.wav --offset-s 3.7 --snr-db 10 --out data\\b.jsonl
    python -m server.tools.make_batches_from_wav data\\song.wav --start 2026-11-24T19:00:00Z   # simulated time

Per window like the device: 48 kHz samples → resample_to_8k → extract_peaks → loudness → Batch → Ed25519 sign.
Default key: the TEST meter M-90 (contract/fixtures/batches/tv_keys.json); use --meter/--seed-file for another.
Default start time: now − (number of windows × 10 s), so the batches are not "late" and end about now.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from math import gcd
from pathlib import Path
from typing import Iterator, Optional

import numpy as np
from scipy.signal import resample_poly

from fairplay_core.constants import CAPTURE_RATE, FP_VERSION, WINDOW_S
from fairplay_core.peaks import extract_peaks, peaks_to_b64, resample_to_8k, rms_dbfs
from fairplay_core.schema import format_utc, parse_utc
from fairplay_core.signing import load_seed, sign_batch
from server.tools.golden_sha import load_wav_float32
from server.tools.make_test_vectors import METER, SEED, VENUE

WIN48 = WINDOW_S * CAPTURE_RATE


def to_48k(x: np.ndarray, sr: int) -> np.ndarray:
    if sr == CAPTURE_RATE:
        return x
    g = gcd(sr, CAPTURE_RATE)
    return resample_poly(x, CAPTURE_RATE // g, sr // g).astype(np.float32)


def windows(x48: np.ndarray, offset_s: float, n: Optional[int], step_s: float) -> Iterator[tuple[int, np.ndarray]]:
    start, i = int(offset_s * CAPTURE_RATE), 0
    while start + WIN48 <= len(x48) and (n is None or i < n):
        yield i, x48[start:start + WIN48]
        start += int(step_s * CAPTURE_RATE)
        i += 1


def make_batches(x48: np.ndarray, *, meter: str = METER, venue: str = VENUE, seed=SEED, seq_start: int = 1,
                 start: Optional[datetime] = None, offset_s: float = 0.0, n: Optional[int] = None,
                 step_s: float = WINDOW_S, snr_db: Optional[float] = None, rng_seed: int = 0,
                 cell_id: str = "624-01-0412-01733", fw: str = "wav-meter-0.1") -> list[dict]:
    rng = np.random.default_rng(rng_seed)
    wins = list(windows(x48, offset_s, n, step_s))
    if start is None:
        start = datetime.now(timezone.utc) - timedelta(seconds=step_s * len(wins))
    out = []
    for i, w in wins:
        if snr_db is not None:   # crowd noise stand-in: white noise at the requested signal-to-noise ratio
            p = float(np.mean(w.astype(np.float64) ** 2)) or 1e-12
            w = (w + rng.normal(0, np.sqrt(p / 10 ** (snr_db / 10)), len(w))).astype(np.float32)
        peaks = extract_peaks(resample_to_8k(w))
        b = {"v": 1, "fp_version": FP_VERSION, "meter_id": meter, "venue_id": venue, "seq": seq_start + i,
             "window_start": format_utc(start + timedelta(seconds=step_s * i)), "window_ms": WINDOW_S * 1000,
             "loudness_db": max(-100.0, min(0.0, rms_dbfs(w))), "cell_id": cell_id, "fw": fw,
             "n_peaks": int(peaks.size), "peaks_b64": peaks_to_b64(peaks)}
        out.append(sign_batch(seed, b))
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("wav")
    ap.add_argument("--meter", default=METER)
    ap.add_argument("--venue", default=VENUE)
    ap.add_argument("--seed-file", help="hex seed file (default: test key of M-90)")
    ap.add_argument("--seq-start", type=int, help="default: based on the current time, so re-runs never collide")
    ap.add_argument("--start", help="window_start of the first batch (UTC, ...Z); default: ends about now")
    ap.add_argument("--offset-s", type=float, default=0.0, help="start this far into the song")
    ap.add_argument("--windows", type=int, help="max number of windows")
    ap.add_argument("--step-s", type=float, default=WINDOW_S, help="10 = demo mode (continuous), 60 = field mode")
    ap.add_argument("--snr-db", type=float, help="add white noise at this SNR")
    ap.add_argument("--post", metavar="URL", help="send to a server (POST /v1/batches)")
    ap.add_argument("--out", help="write JSONL here")
    a = ap.parse_args(argv)

    x, sr = load_wav_float32(Path(a.wav))
    seed = load_seed(a.seed_file) if a.seed_file else SEED
    seq_start = a.seq_start or int(datetime.now(timezone.utc).timestamp()) % 10**9
    batches = make_batches(to_48k(x, sr), meter=a.meter, venue=a.venue, seed=seed, seq_start=seq_start,
                           start=parse_utc(a.start) if a.start else None, offset_s=a.offset_s, n=a.windows,
                           step_s=a.step_s, snr_db=a.snr_db)
    print(f"{len(batches)} batches from {a.wav} (meter {a.meter}, seq {seq_start}+, offset {a.offset_s}s"
          f"{f', SNR {a.snr_db} dB' if a.snr_db is not None else ''})")
    if a.out:
        Path(a.out).write_text("".join(json.dumps(b) + "\n" for b in batches), encoding="utf-8")
        print(f"wrote {a.out}")
    if a.post:
        import httpx
        with httpx.Client(base_url=a.post, timeout=10) as c:
            for b in batches:
                r = c.post("/v1/batches", json=b)
                print(f"  seq {b['seq']} {b['window_start']} peaks {b['n_peaks']:3} -> {r.status_code} {r.json()}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
