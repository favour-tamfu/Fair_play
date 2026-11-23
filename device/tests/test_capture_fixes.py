"""Tests for the recorder fixes: gap markers, device check, debug folder."""
import os

import numpy as np
import sounddevice as sd

from device.agent import capture
from device.agent.scheduler import Scheduler
from fairplay_core.constants import CAPTURE_RATE


def _blocks(x, t0, blocksize=4800):
    for i in range(0, x.size, blocksize):
        yield t0 + i / CAPTURE_RATE, x[i : i + blocksize]


def test_gap_restarts_windows_at_the_next_block():
    seg_a = np.zeros(5 * CAPTURE_RATE, dtype=np.float32)    # 5 s: too short for a window
    seg_b = np.zeros(25 * CAPTURE_RATE, dtype=np.float32)   # 25 s: two demo windows
    stream = list(_blocks(seg_a, 1000.0)) + [None] + list(_blocks(seg_b, 5000.0))
    starts = [w.start_utc for w in Scheduler("demo").windows(stream)]
    # the 5 s before the gap is discarded; windows start from the block after the gap
    assert starts == [5000.0, 5010.0]


def test_no_gap_marker_keeps_the_normal_timing():
    x = np.zeros(25 * CAPTURE_RATE, dtype=np.float32)
    starts = [w.start_utc for w in Scheduler("demo").windows(_blocks(x, 1000.0))]
    assert starts == [1000.0, 1010.0]


def test_wasapi_input_is_skipped_when_it_cannot_open(monkeypatch):
    monkeypatch.setattr(sd, "query_hostapis", lambda: [{"name": "Windows WASAPI", "default_input_device": 9}])

    def refuse(**kwargs):
        raise sd.PortAudioError("Invalid sample rate")

    monkeypatch.setattr(sd, "check_input_settings", refuse)
    assert capture.MicSource._pick_wasapi_input() is None


def test_wasapi_input_is_used_when_it_opens(monkeypatch):
    monkeypatch.setattr(sd, "query_hostapis", lambda: [{"name": "Windows WASAPI", "default_input_device": 9}])
    monkeypatch.setattr(sd, "check_input_settings", lambda **kwargs: None)
    assert capture.MicSource._pick_wasapi_input() == 9


def test_debug_folder_is_under_the_repo_not_the_working_folder():
    assert os.path.isabs(capture.DEBUG_DIR)
    assert capture.DEBUG_DIR.endswith(os.path.join("data", "debug"))
    assert os.path.isdir(os.path.join(capture.REPO_ROOT, "device"))
