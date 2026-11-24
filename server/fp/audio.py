"""Decode any uploaded audio file to 8 kHz mono float32 — catalogue side of brief §5.1 step 1.

Primary: ffmpeg (`-ac 1 -ar 8000 -f f32le`), installed in the server image.
Fallback (host without ffmpeg, e.g. tests on Windows): WAV only, scipy + resample_poly, exactly like the device.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
from math import gcd
from pathlib import Path

import numpy as np
from scipy.signal import resample_poly

from fairplay_core.constants import SAMPLE_RATE

log = logging.getLogger(__name__)


class DecodeError(Exception):
    pass


def have_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def decode_8k(path: Path) -> np.ndarray:
    if have_ffmpeg():
        p = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-i", str(path), "-ac", "1", "-ar", str(SAMPLE_RATE),
                            "-f", "f32le", "-"], capture_output=True, timeout=300)
        if p.returncode != 0:
            raise DecodeError(p.stderr.decode("utf-8", "replace").strip()[-500:] or "ffmpeg failed")
        x = np.frombuffer(p.stdout, dtype="<f4").astype(np.float32)
    elif path.suffix.lower() == ".wav":
        from server.tools.golden_sha import load_wav_float32
        try:
            x, sr = load_wav_float32(path)
        except ValueError as e:
            raise DecodeError(f"cannot read WAV: {e}") from e
        if sr != SAMPLE_RATE:
            g = gcd(sr, SAMPLE_RATE)
            x = resample_poly(x, SAMPLE_RATE // g, sr // g).astype(np.float32)
    else:
        raise DecodeError("ffmpeg not installed; only .wav can be decoded on this machine")
    if len(x) < 512:
        raise DecodeError("audio shorter than one analysis frame (64 ms)")
    return x
