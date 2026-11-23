"""Tests for core/fairplay_core/peaks.py (A-T01, plan section 3)."""
import hashlib
import pathlib
import time

import numpy as np
import pytest

from fairplay_core.constants import (
    BIN_MAX,
    BIN_MIN,
    BLOCK_FRAMES,
    FRAMES_PER_WINDOW,
    PEAKS_PER_BLOCK,
    SAMPLE_RATE,
    WINDOW_SAMPLES,
)
from fairplay_core.peaks import (
    extract_peaks,
    pack_peaks,
    peaks_to_b64,
    b64_to_peaks,
    rms_dbfs,
    unpack_peaks,
)

GOLDEN = pathlib.Path(__file__).parent / "golden" / "tone_mix.sha256"


def _tone_mix(seed: int = 0) -> np.ndarray:
    """10 s: 1000 Hz tone plus very low noise (deterministic)."""
    t = np.arange(WINDOW_SAMPLES) / SAMPLE_RATE
    rng = np.random.default_rng(seed)
    x = 0.5 * np.sin(2 * np.pi * 1000.0 * t) + 1e-4 * rng.standard_normal(t.size)
    return x.astype(np.float32)


def test_sine_peak_is_at_1000hz_bin():
    peaks = extract_peaks(_tone_mix())
    assert peaks.size > 0
    # 1000 Hz / 15.625 Hz per bin = bin 64. A stationary tone is a local maximum only in
    # frames where its small noise ripple peaks, so it yields few peaks; the guarantee
    # is that the strongest peak in each block is the tone.
    for b in np.unique(peaks["frame"] // BLOCK_FRAMES):
        block = peaks[peaks["frame"] // BLOCK_FRAMES == b]
        strongest = block[np.argmax(block["mag_db"])]
        assert abs(int(strongest["bin"]) - 64) <= 1, f"block {b}: strongest at bin {strongest['bin']}"


def test_two_tones_alternating_bins():
    t = np.arange(WINDOW_SAMPLES) / SAMPLE_RATE
    seg = (t // 0.5).astype(int) % 2  # 0 -> 440 Hz, 1 -> 2000 Hz
    x = np.where(seg == 0, np.sin(2 * np.pi * 440 * t), np.sin(2 * np.pi * 2000 * t)).astype(np.float32)
    peaks = extract_peaks(x)
    bins = set(np.unique(peaks["bin"]).tolist())
    # 440 Hz -> bin 28, 2000 Hz -> bin 128
    assert any(abs(b - 28) <= 1 for b in bins)
    assert any(abs(b - 128) <= 1 for b in bins)
    # Each tone's peaks should sit in its own half-second segment (frame centre -> sample).
    def segment_of(frame):
        centre = int(frame) * 256 + 256
        return int(seg[min(centre, WINDOW_SAMPLES - 1)])

    low = peaks[np.abs(peaks["bin"].astype(int) - 28) <= 1]
    high = peaks[np.abs(peaks["bin"].astype(int) - 128) <= 1]
    assert low.size > 0 and high.size > 0
    assert np.mean([segment_of(f) == 0 for f in low["frame"]]) > 0.9
    assert np.mean([segment_of(f) == 1 for f in high["frame"]]) > 0.9
    assert peaks["frame"].max() < FRAMES_PER_WINDOW


def test_frame_count_for_10s_window():
    from fairplay_core.peaks import spectrogram_db

    assert spectrogram_db(np.zeros(WINDOW_SAMPLES, dtype=np.float32)).shape[0] == 311
    assert FRAMES_PER_WINDOW == 311


def test_pack_unpack_roundtrip_within_quantisation():
    peaks = extract_peaks(_tone_mix())
    back = unpack_peaks(pack_peaks(peaks))
    assert back.size == peaks.size
    assert np.array_equal(back["frame"], peaks["frame"])
    assert np.array_equal(back["bin"], peaks["bin"])
    assert np.max(np.abs(back["mag_db"] - peaks["mag_db"])) <= 0.25 + 1e-6
    # base64 path too
    again = b64_to_peaks(peaks_to_b64(peaks))
    assert np.array_equal(again["frame"], back["frame"])


TONE_WAV = pathlib.Path(__file__).parent / "data" / "tone_mix.wav"


def load_wav_for_golden(path) -> np.ndarray:
    """The one WAV-loading recipe for the MC0 golden SHA (agreed with B, REQUESTS R-001).

    scipy.io.wavfile.read -> int16/32768, int32/2**31, uint8 (x-128)/128, float as is ->
    float32, stereo -> mean of channels; 8000 Hz used as is; 48000 Hz -> resample_to_8k.
    """
    from scipy.io import wavfile

    from fairplay_core.peaks import resample_to_8k

    sr, data = wavfile.read(str(path))
    if data.dtype == np.int16:
        x = data.astype(np.float32) / 32768.0
    elif data.dtype == np.int32:
        x = data.astype(np.float32) / float(2**31)
    elif data.dtype == np.uint8:
        x = (data.astype(np.float32) - 128.0) / 128.0
    elif data.dtype == np.float32:
        x = data
    else:
        raise ValueError(f"unsupported WAV dtype {data.dtype}")
    if x.ndim == 2:
        x = x.mean(axis=1)
    x = np.asarray(x, dtype=np.float32)
    if sr == SAMPLE_RATE:
        return x
    if sr == 48000:
        return resample_to_8k(x)
    raise ValueError(f"unsupported sample rate {sr}")


def test_determinism_and_golden_hash():
    digest_1 = hashlib.sha256(pack_peaks(extract_peaks(load_wav_for_golden(TONE_WAV)))).hexdigest()
    digest_2 = hashlib.sha256(pack_peaks(extract_peaks(load_wav_for_golden(TONE_WAV)))).hexdigest()
    assert digest_1 == digest_2
    assert GOLDEN.exists(), f"missing golden file {GOLDEN}; write it once, then commit it"
    assert GOLDEN.read_text().split()[0] == digest_1


def test_density_cap_per_block():
    peaks = extract_peaks(np.random.default_rng(1).standard_normal(WINDOW_SAMPLES).astype(np.float32))
    blocks = peaks["frame"] // BLOCK_FRAMES
    counts = np.bincount(blocks)
    assert counts.max() <= PEAKS_PER_BLOCK


def test_performance_one_window_warn_only(capsys):
    x = _tone_mix()
    extract_peaks(x)  # warm-up
    t0 = time.perf_counter()
    extract_peaks(x)
    ms = (time.perf_counter() - t0) * 1000
    print(f"extract_peaks one 10 s window: {ms:.1f} ms")
    if ms > 150:
        import warnings

        warnings.warn(f"extract_peaks took {ms:.1f} ms (> 150 ms target)")


def test_out_of_band_bins_never_peak():
    rng = np.random.default_rng(2)
    x = rng.standard_normal(WINDOW_SAMPLES).astype(np.float32)
    x += 0.8 * np.sin(2 * np.pi * 60 * np.arange(WINDOW_SAMPLES) / SAMPLE_RATE)  # 60 Hz hum, bin 4
    x += 0.8 * np.sin(2 * np.pi * 3900 * np.arange(WINDOW_SAMPLES) / SAMPLE_RATE)  # above band
    peaks = extract_peaks(x)
    assert peaks["bin"].min() >= BIN_MIN
    assert peaks["bin"].max() <= BIN_MAX


def test_rms_dbfs_rounding():
    assert rms_dbfs(np.ones(100)) == 0.0
    assert rms_dbfs(np.zeros(100)) <= -199.0
