"""Tests for device/agent/capture.py and scheduler.py (A-T02)."""
from types import SimpleNamespace

import numpy as np
import pytest

from device.agent.capture import FileSource, wall_time_of_block
from device.agent.scheduler import Scheduler, WINDOW_SAMPLES_48
from fairplay_core.constants import CAPTURE_RATE, SAMPLE_RATE


def _tone_48k(seconds: float, seed: int = 0) -> np.ndarray:
    t = np.arange(int(seconds * CAPTURE_RATE)) / CAPTURE_RATE
    rng = np.random.default_rng(seed)
    return (0.4 * np.sin(2 * np.pi * 440 * t) + 0.01 * rng.standard_normal(t.size)).astype(np.float32)


def _blocks(x: np.ndarray, blocksize: int = 4800, t0: float = 1_000_000.0):
    for i in range(0, x.size, blocksize):
        yield t0 + i / CAPTURE_RATE, x[i : i + blocksize]


def test_file_source_demo_windows_have_spec_sizes(tmp_path):
    import soundfile as sf

    path = tmp_path / "t.wav"
    sf.write(path, _tone_48k(25), CAPTURE_RATE, subtype="FLOAT")
    windows = list(Scheduler("demo").windows(FileSource(str(path), start_utc=1_000_000.0).blocks()))
    assert len(windows) == 2                      # starts at 0 s and 10 s; 25 s audio
    for w in windows:
        assert w.samples48.size == 480_000        # 10 s at 48 kHz
        assert w.x8.size == 80_000                # 10 s at 8 kHz
        assert w.peaks.size > 0                   # a tone gives peaks
        assert -100.0 <= w.loudness_db <= 0.0


def test_demo_start_times_step_by_10s():
    x = _tone_48k(35)
    starts = [w.start_utc for w in Scheduler("demo").windows(_blocks(x))]
    assert len(starts) == 3
    assert np.allclose(np.diff(starts), 10.0)


def test_field_start_times_step_by_60s():
    x = _tone_48k(135)                            # third window starts at 120 s and ends at 130 s
    starts = [w.start_utc for w in Scheduler("field").windows(_blocks(x))]
    assert len(starts) == 3                       # starts at 0, 60, 120 s
    assert np.allclose(np.diff(starts), 60.0)


def test_short_input_yields_no_window():
    assert list(Scheduler("demo").windows(_blocks(_tone_48k(9)))) == []


def test_windows_do_not_depend_on_block_size():
    x = _tone_48k(25)
    a = [w.samples48 for w in Scheduler("demo").windows(_blocks(x, blocksize=4800))]
    b = [w.samples48 for w in Scheduler("demo").windows(_blocks(x, blocksize=7001))]
    assert len(a) == len(b) == 2
    for u, v in zip(a, b):
        assert np.array_equal(u, v)


def test_bad_mode_is_rejected():
    with pytest.raises(ValueError):
        Scheduler("nightly")


def test_window_length_constant():
    assert WINDOW_SAMPLES_48 == 480_000


def test_wall_time_of_block_subtracts_input_latency():
    # block captured 0.25 s before the stream clock said 100.0 s; callback runs at wall 1_700.0
    info = SimpleNamespace(currentTime=100.0, inputBufferAdcTime=99.75)
    assert wall_time_of_block(info, now=1_700.0) == pytest.approx(1_699.75)


def test_file_source_is_resampled_to_48k(tmp_path):
    import soundfile as sf

    x8 = np.sin(2 * np.pi * 440 * np.arange(SAMPLE_RATE * 2) / SAMPLE_RATE).astype(np.float32)
    path = tmp_path / "t8.wav"
    sf.write(path, x8, SAMPLE_RATE, subtype="FLOAT")
    loaded = FileSource(str(path)).load()
    assert loaded.size == CAPTURE_RATE * 2


def test_window_times_follow_the_clock_after_a_sleep():
    """R-020: the stream resumes after a sleep without a gap marker; windows must use the new wall time."""
    x = _tone_48k(25)
    def blocks():
        yield from _blocks(x, t0=1_000_000.0)              # 25 s of audio, then the laptop sleeps for an hour
        yield from _blocks(x, t0=1_000_000.0 + 3600.0)     # audio resumes, no None in between
    sch = Scheduler("demo")
    starts = [w.start_utc for w in sch.windows(blocks())]
    assert starts == pytest.approx([1_000_000.0, 1_000_010.0, 1_003_600.0, 1_003_610.0])
    assert sch.reanchors == 1


def test_small_clock_jitter_does_not_reanchor():
    x = _tone_48k(35)
    rng = np.random.default_rng(1)
    jittered = ((t + rng.uniform(-0.05, 0.05), b) for t, b in _blocks(x))   # callback timing jitter of ±50 ms
    sch = Scheduler("demo")
    starts = [w.start_utc for w in sch.windows(jittered)]
    assert len(starts) == 3 and sch.reanchors == 0
