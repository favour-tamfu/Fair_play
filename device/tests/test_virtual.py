"""Tests for the virtual meter (A-T07): playlist, noise mixing, block timing, simulated run."""
import json
import os

import numpy as np
import pytest

from device.tests.test_uploader_faults import Resp
from device.virtual.__main__ import make_blocks, mix_noise, read_playlist, run_pipeline
from fairplay_core.constants import CAPTURE_RATE


def test_playlist_skips_comments_and_resolves_relative_paths(tmp_path):
    pl = tmp_path / "list.txt"
    pl.write_text("# evening set\nsong_a.wav\n\n  song_b.wav  \n", encoding="utf-8")
    items = read_playlist(str(pl))
    assert [os.path.basename(i) for i in items] == ["song_a.wav", "song_b.wav"]
    assert all(os.path.isabs(i) for i in items)


def test_noise_is_mixed_at_the_requested_snr():
    rng = np.random.default_rng(0)
    audio = (0.5 * np.sin(np.linspace(0, 200, 96000))).astype(np.float32)
    noise = rng.standard_normal(40000).astype(np.float32)
    mixed = mix_noise(audio, noise, snr_db=10.0)
    added = mixed - audio
    snr = 10 * np.log10(np.mean(audio ** 2) / np.mean(added ** 2))
    assert abs(snr - 10.0) < 0.1


def test_no_noise_leaves_the_audio_alone():
    audio = np.ones(100, dtype=np.float32)
    assert np.array_equal(mix_noise(audio, np.zeros(0, dtype=np.float32), 10.0), audio)


def test_blocks_are_0_1_s_apart_and_realtime_sleeps_between_them():
    audio = np.zeros(CAPTURE_RATE, dtype=np.float32)  # 1 s
    slept = []
    blocks = list(make_blocks(audio, 1000.0, realtime=True, speed=2.0, sleep=slept.append))
    assert len(blocks) == 10
    assert np.allclose(np.diff([t for t, _ in blocks]), 0.1)
    assert len(slept) == 10 and all(abs(s - 0.05) < 1e-9 for s in slept)  # speed 2 halves the wait


@pytest.mark.skipif(not os.path.exists(os.path.join("device", "secrets", "M-11.seed")),
                    reason="needs the M-11 seed, which lives only on Laptop A (secrets are not in git)")
def test_simulated_run_stamps_windows_from_the_simulated_start(tmp_path):
    class OkClient:
        def post(self, path, json=None, timeout=None):
            if path == "/v1/batches":
                return Resp(200, {"ack": json["seq"], "status": "stored"})
            if path == "/v1/heartbeat":
                return Resp(200, {"ok": True, "server_time": "2026-11-24T19:00:00.000Z"})
            return Resp(200, {"results": []})

    cfg = {"meter_id": "M-11", "venue_id": "V-DLA-AKWA01", "fw": "agent-0.1.0", "heartbeat_s": 3600}
    audio = np.zeros(25 * CAPTURE_RATE, dtype=np.float32)
    start = 1_000_000.0
    made = run_pipeline(cfg, "demo", make_blocks(audio, start, realtime=False), "virtual test",
                        state_dir=str(tmp_path), show_screen=False, client=OkClient())
    assert made == 2
    events = [json.loads(line) for line in open(tmp_path / "M-11_events.jsonl", encoding="utf-8")]
    stamps = [e["window_start"] for e in events if e["event"] == "window"]
    assert stamps == ["1970-01-12T13:46:40.000Z", "1970-01-12T13:46:50.000Z"]
    assert sum(1 for e in events if e["event"] == "acked") == 2
