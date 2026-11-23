"""MC0 golden check: SHA-256 of pack_peaks(extract_peaks(<wav>)). Both laptops must print the same value.

    python -m server.tools.golden_sha [core/tests/data/tone_mix.wav]

WAV loading recipe (proposed to A in REQUESTS R-001, so both sides hash the same samples):
scipy.io.wavfile.read → int16 / 32768, int32 / 2**31, uint8 (x-128)/128, float as is → float32; stereo → mean of
channels; 8000 Hz used as is, 48000 Hz → peaks.resample_to_8k; any other rate is an error.
Exit codes: 0 ok, 3 = waiting for A (peaks.py or the WAV not there yet).
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import numpy as np
from scipy.io import wavfile

DEFAULT = Path(__file__).resolve().parents[2] / "core" / "tests" / "data" / "tone_mix.wav"


def load_wav_float32(path: Path) -> tuple[np.ndarray, int]:
    sr, x = wavfile.read(path)
    if x.dtype == np.int16:
        x = x.astype(np.float32) / 32768.0
    elif x.dtype == np.int32:
        x = x.astype(np.float32) / 2.0 ** 31
    elif x.dtype == np.uint8:
        x = (x.astype(np.float32) - 128.0) / 128.0
    else:
        x = x.astype(np.float32)
    if x.ndim == 2:
        x = x.mean(axis=1, dtype=np.float32)
    return x, sr


def main(argv: list[str]) -> int:
    path = Path(argv[0]) if argv else DEFAULT
    try:
        from fairplay_core import peaks  # A-T01
    except ImportError:
        print("SKIP golden SHA: fairplay_core.peaks not merged yet (A-T01)")
        return 3
    if not path.exists():
        print(f"SKIP golden SHA: {path} not found (A-T01 creates it)")
        return 3
    x, sr = load_wav_float32(path)
    if sr == 48000:
        x = peaks.resample_to_8k(x)
    elif sr != 8000:
        print(f"ERROR: {path} is {sr} Hz; expected 8000 or 48000")
        return 1
    p = peaks.extract_peaks(x)
    sha = hashlib.sha256(peaks.pack_peaks(p)).hexdigest()
    print(f"golden SHA {path.name}: {sha}  ({len(p)} peaks)")
    golden = path.parents[1] / "golden" / (path.stem + ".sha256")
    if golden.exists():
        expected = golden.read_text().split()[0]
        print(f"A's golden file:       {expected}  -> {'MATCH' if expected == sha else 'MISMATCH'}")
        return 0 if expected == sha else 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
