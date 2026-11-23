"""Peak extraction (fp-1.0, brief section 5.1). Owner: Agent A.

Shared by the device (Laptop A) and the catalogue (Laptop B). Any change to
these parameters is a contract change (docs/02 section 6).
"""
import base64

import numpy as np
from scipy.ndimage import maximum_filter, uniform_filter
from scipy.signal import get_window, resample_poly

from fairplay_core.constants import (
    BIN_MAX,
    BIN_MIN,
    BLOCK_FRAMES,
    CAPTURE_RATE,
    HOP,
    MAG_OFFSET_DB,
    MAG_SCALE,
    N_FFT,
    PEAK_NEIGHBORHOOD,
    PEAKS_PER_BLOCK,
    SAMPLE_RATE,
    THRESH_DB,
    THRESH_NEIGHBORHOOD,
)

PEAK_DTYPE = np.dtype([("frame", "<i4"), ("bin", "<i2"), ("mag_db", "<f4")])
WIRE_DTYPE = np.dtype([("frame", "<u2"), ("bin", "u1"), ("mag", "u1")])  # "<HBB"

_WINDOW = get_window("hann", N_FFT, fftbins=True)


def resample_to_8k(x48: np.ndarray) -> np.ndarray:
    """48 kHz capture -> 8 kHz analysis rate (resample_poly up=1, down=6)."""
    if CAPTURE_RATE // SAMPLE_RATE != 6:
        raise ValueError("resample_to_8k assumes CAPTURE_RATE / SAMPLE_RATE == 6")
    return resample_poly(np.asarray(x48, dtype=np.float32), up=1, down=6).astype(np.float32)


def spectrogram_db(x8: np.ndarray) -> np.ndarray:
    """Magnitude spectrogram in dB, shape (frames, N_FFT//2 + 1), no edge padding."""
    x = np.asarray(x8, dtype=np.float32)
    if x.ndim != 1 or x.size < N_FFT:
        raise ValueError("need a 1-D signal of at least N_FFT samples")
    # sliding_window_view gives every start position; take every HOP-th one.
    frames = np.lib.stride_tricks.sliding_window_view(x, N_FFT)[::HOP]
    spec = np.fft.rfft(frames * _WINDOW, axis=1)
    return (20.0 * np.log10(np.abs(spec) + 1e-9)).astype(np.float32)


def extract_peaks(x8: np.ndarray) -> np.ndarray:
    """Spectral peaks: frame (int32), bin (int16), mag_db (float32), sorted by (frame, bin)."""
    S = spectrogram_db(x8)
    n_frames, n_bins = S.shape
    in_band = np.zeros(n_bins, dtype=bool)
    in_band[BIN_MIN : BIN_MAX + 1] = True

    # Step 4: out-of-band bins can never be peaks.
    Sb = np.where(in_band[None, :], S, np.float32(-np.inf))

    # Step 5: local maximum over (21 frames x 31 bins), constant edges with -inf.
    local_max = maximum_filter(Sb, size=PEAK_NEIGHBORHOOD, mode="constant", cval=-np.inf)
    is_max = (Sb == local_max) & np.isfinite(Sb)

    # Step 6: local threshold from a (63 x 31) mean over the band.
    band_vals = S[:, in_band]
    band_min = float(band_vals.min())
    filled = np.where(in_band[None, :], S, np.float32(band_min))
    local_mean = uniform_filter(filled, size=THRESH_NEIGHBORHOOD, mode="nearest")
    is_loud = Sb > (local_mean + THRESH_DB)

    f_idx, b_idx = np.nonzero(is_max & is_loud)
    mags = Sb[f_idx, b_idx]

    # Step 7: density cap, strongest PEAKS_PER_BLOCK peaks per block of BLOCK_FRAMES frames.
    block = f_idx // BLOCK_FRAMES
    order = np.lexsort((-mags, block))  # within each block, strongest first
    f_idx, b_idx, mags, block = f_idx[order], b_idx[order], mags[order], block[order]
    rank = np.arange(block.size) - np.searchsorted(block, block, side="left")
    keep = rank < PEAKS_PER_BLOCK
    f_idx, b_idx, mags = f_idx[keep], b_idx[keep], mags[keep]

    # Step 8: deterministic output order.
    out = np.zeros(f_idx.size, dtype=PEAK_DTYPE)
    out["frame"] = f_idx
    out["bin"] = b_idx
    out["mag_db"] = mags
    out.sort(order=["frame", "bin"])
    return out


def pack_peaks(peaks) -> bytes:
    """Quantise and pack as little-endian <HBB records (step 9)."""
    if peaks.size and int(peaks["frame"].max()) >= 65536:
        raise ValueError("frame index does not fit in u16")
    wire = np.zeros(peaks.size, dtype=WIRE_DTYPE)
    wire["frame"] = peaks["frame"]
    wire["bin"] = peaks["bin"]
    mag_u8 = np.clip(np.round(MAG_SCALE * (peaks["mag_db"].astype(np.float64) + MAG_OFFSET_DB)), 0, 255)
    wire["mag"] = mag_u8.astype(np.uint8)
    return wire.tobytes()


def unpack_peaks(b: bytes) -> np.ndarray:
    """Inverse of pack_peaks; mag_db is de-quantised (0.5 dB steps)."""
    wire = np.frombuffer(b, dtype=WIRE_DTYPE)
    out = np.zeros(wire.size, dtype=PEAK_DTYPE)
    out["frame"] = wire["frame"].astype(np.int32)
    out["bin"] = wire["bin"].astype(np.int16)
    out["mag_db"] = (wire["mag"].astype(np.float32) / MAG_SCALE) - MAG_OFFSET_DB
    return out


def peaks_to_b64(peaks) -> str:
    return base64.b64encode(pack_peaks(peaks)).decode("ascii")


def b64_to_peaks(s: str) -> np.ndarray:
    return unpack_peaks(base64.b64decode(s))


def rms_dbfs(x: np.ndarray) -> float:
    """RMS level in dBFS, rounded to 1 decimal."""
    x = np.asarray(x, dtype=np.float64)
    rms = float(np.sqrt(np.mean(np.square(x)))) if x.size else 0.0
    level = 20.0 * np.log10(rms + 1e-12)
    # Contract c-1.0 §3.1: loudness_db is in -100..0. Silence floors at -100; clipped input caps at 0.
    return round(float(min(0.0, max(-100.0, level))), 1)
