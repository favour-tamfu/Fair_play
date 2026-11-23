"""Write the contract batch test vectors (contract §3.4) into contract/fixtures/batches/.

    python -m server.tools.make_test_vectors

Deterministic: fixed TEST-ONLY key and seeded synthetic peaks, so re-running gives byte-identical files.
- tv_keys.json             test meter M-90: seed (hex, test only!) + public key
- tv_batch_valid.json      valid signed batch                              → server 200 stored
- tv_batch_badsig.json     one byte of the peaks changed after signing     → server 401 bad_signature
                           (a magnitude byte, so the batch is still well-formed and only the signature is wrong)
- tv_batch_badversion.json fp_version "fp-0.9", correctly signed           → server 422 invalid
"""
from __future__ import annotations

import base64
import hashlib
import json
import struct
from pathlib import Path

import numpy as np

from fairplay_core.constants import BIN_MAX, BIN_MIN, FP_VERSION, FRAMES_PER_WINDOW
from fairplay_core.signing import make_pub_record, sign_batch

OUT = Path(__file__).resolve().parents[2] / "contract" / "fixtures" / "batches"
SEED = hashlib.sha256(b"fair-play test vector key - NOT A REAL METER").digest()
METER, VENUE = "M-90", "V-BUEA-CIMFEST"


def synthetic_peaks(n_peaks: int = 287, seed: int = 1) -> bytes:
    rng = np.random.default_rng(seed)
    frames = np.sort(rng.integers(0, FRAMES_PER_WINDOW, n_peaks))
    bins = rng.integers(BIN_MIN, BIN_MAX + 1, n_peaks)
    mags = rng.integers(80, 220, n_peaks)
    return b"".join(struct.pack("<HBB", int(f), int(b), int(m)) for f, b, m in zip(frames, bins, mags))


def unsigned_batch(peaks: bytes, **over) -> dict:
    d = {"v": 1, "fp_version": FP_VERSION, "meter_id": METER, "venue_id": VENUE, "seq": 1,
         "window_start": "2026-11-24T21:14:00.000Z", "window_ms": 10000, "loudness_db": -18.4,
         "cell_id": "624-01-0412-01733", "fw": "testvector-1", "n_peaks": len(peaks) // 4,
         "peaks_b64": base64.b64encode(peaks).decode("ascii")}
    d.update(over)
    return d


def build() -> dict[str, dict]:
    peaks = synthetic_peaks()
    valid = sign_batch(SEED, unsigned_batch(peaks))

    tampered = bytearray(peaks)
    tampered[3] ^= 0x01                      # byte 3 = magnitude of the first peak
    badsig = {**valid, "peaks_b64": base64.b64encode(bytes(tampered)).decode("ascii")}

    badversion = sign_batch(SEED, unsigned_batch(peaks, seq=2, fp_version="fp-0.9"))

    keys = {**make_pub_record(METER, VENUE, SEED), "created_at": "2026-11-23T21:00:00Z",
            "seed_hex": SEED.hex(), "note": "TEST ONLY - this seed is public; never use it for a real meter"}
    return {"tv_keys.json": keys, "tv_batch_valid.json": valid, "tv_batch_badsig.json": badsig,
            "tv_batch_badversion.json": badversion}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, doc in build().items():
        (OUT / name).write_bytes((json.dumps(doc, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
        print(f"wrote {OUT / name}")


if __name__ == "__main__":
    main()
