"""Tests for device/agent/capture.py and scheduler.py (A-T02)."""
import numpy as np
import pytest
import soundfile as sf

from fairplay_core.constants import CAPTURE_RATE, SAMPLE_RATE
from device.agent.capture import FileSource
from device.agent.scheduler import Scheduler, WINDOW_SAMPLES_48


def _write_wav(path, seconds):
    t = np.arange(int(seconds * CAPTURE_RATE)) / CAPTURE_RATE
    x = (0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    sf.write(path, x, CAPTURE_RATE, subtype="FLOAT")
    return path


def _blocks_from_array(x, blocksize=4800, t0=1_000_000.0):
    for i in range(0, x.size, blocksize):
        yield t0 + i / CAPTURE_RATE, x[i : i + blocksize]


def test_file_source_demo_windows_have_expected_sizes(tmp_path):
    wav = _write_wav(tmp_path / "tone.wav", seconds=25)
    src = FileSource(str(wav), realtime=False, start_utc=1_000_000.0)
    windows = list(Scheduler("demo").windows(src.blocks()))
    assert len(windows) == 2  # 25 s -> two complete 10 s windows
    for w in windows:
        assert w.samples48.size == 480_000
        assert w.x8.size == 80_000
        assert w.peaks.size > 0  # a steady tone yields peaks
        assert isinstance(w.loudness_db, float)


def test_demo_window_starts_are_10s_apart(tmp_path):
    wav = _write_wav(tmp_path / "tone.wav", seconds=35)
    src = FileSource(str(wav), start_utc=1_000_000.0)
    starts = [w.start_utc for w in Scheduler("demo").windows(src.blocks())]
    assert len(starts) == 3
    assert np.allclose(np.diff(starts), 10.0)
    assert starts[0] == pytest.approx(1_000_000.0)


def test_field_mode_skips_50s_between_windows():
    # 130 s of audio -> windows at 0, 60, 120 s; the last one fits exactly (120 + 10 <= 130).
    x = np.zeros(130 * CAPTURE_RATE, dtype=np.float32)
    starts = [w.start_utc for w in Scheduler("field").windows(_blocks_from_array(x))]
    assert len(starts) == 3
    assert np.allclose(np.diff(starts), 60.0)


def test_partial_window_is_not_emitted():
    x = np.zeros(WINDOW_SAMPLES_48 - 1, dtype=np.float32)
    assert list(Scheduler("demo").windows(_blocks_from_array(x))) == []


def test_demo_window_content_matches_input_regardless_of_block_size():
    rng = np.random.default_rng(3)
    x = rng.standard_normal(2 * WINDOW_SAMPLES_48).astype(np.float32)
    a = [w.samples48 for w in Scheduler("demo").windows(_blocks_from_array(x, blocksize=4800))]
    b = [w.samples48 for w in Scheduler("demo").windows(_blocks_from_array(x, blocksize=7001))]
    assert len(a) == len(b) == 2
    for wa, wb, wx in zip(a, b, [x[:WINDOW_SAMPLES_48], x[WINDOW_SAMPLES_48:]]):
        assert np.array_equal(wa, wx)
        assert np.array_equal(wb, wx)


def test_bad_mode_rejected():
    with pytest.raises(ValueError):
        Scheduler("nightly")


def test_file_source_resamples_non_48k_input(tmp_path):
    t = np.arange(int(12 * SAMPLE_RATE)) / SAMPLE_RATE
    x = (0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    path = tmp_path / "tone_8k.wav"
    sf.write(path, x, SAMPLE_RATE, subtype="FLOAT")
    loaded = FileSource(str(path)).load()
    assert abs(loaded.size - 12 * CAPTURE_RATE) <= 2
