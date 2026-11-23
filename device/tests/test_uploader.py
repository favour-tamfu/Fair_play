"""Tests for the uploader and heartbeat (A-T05) against the fake SONACAM."""
import base64
import os
import threading

import nacl.signing
import numpy as np
import pytest
from fastapi.testclient import TestClient

from device.agent.batcher import build_batch
from device.agent.outbox import Outbox
from device.agent.state import MeterState
from device.agent.uploader import Uploader
from device.tools.fake_sonacam import create_app
from fairplay_core.peaks import extract_peaks

CFG = {"meter_id": "M-96", "venue_id": "V-TEST-UP0001", "cell_id": "624-01-0412-01733", "fw": "agent-test"}


class Rig:
    """One fake server, one outbox, one meter key."""

    def __init__(self, tmp_path):
        key = nacl.signing.SigningKey.generate()
        self.seed = bytes(key)
        pub = base64.b64encode(bytes(key.verify_key)).decode("ascii")
        self.server = create_app({"M-96": pub})
        self.client = TestClient(self.server)
        MeterState("M-96", state_dir=str(tmp_path))
        self.outbox = Outbox(os.path.join(str(tmp_path), "M-96.db"))
        t = np.arange(80_000) / 8_000
        self.peaks = extract_peaks((0.5 * np.sin(2 * np.pi * 1000 * t)).astype(np.float32))
        self.uploader = Uploader(self.outbox, self.client, CFG, self.seed, sleep=lambda s: None, rand=lambda: 0.5)

    def batch(self, seq, loud=-18.4):
        return build_batch(CFG, seq=seq, window_start_utc=1_790_000_000.0, peaks=self.peaks, loudness_db=loud, seed=self.seed)

    def stored(self):
        return self.client.get("/_stored").json()["count"]

    def set_chaos(self, **kw):
        self.client.post("/_chaos", json=kw)


@pytest.fixture
def rig(tmp_path):
    return Rig(tmp_path)


def _drain(rig, max_rounds=5000):
    for _ in range(max_rounds):
        if rig.outbox.count() == 0:
            return True
        rig.uploader.drain_once()
    return rig.outbox.count() == 0


def test_hundred_batches_with_half_failing_all_arrive_once(rig):
    rig.set_chaos(fail_rate=0.5)
    for seq in range(1, 101):
        rig.outbox.put(rig.batch(seq))
    assert _drain(rig)
    assert rig.stored() == 100          # none lost
    assert rig.outbox.dead_count() == 0
    assert rig.uploader.acked == 100    # acked once each, no duplicates counted


def test_server_down_then_up_drains(rig):
    for seq in range(1, 4):
        rig.outbox.put(rig.batch(seq))
    rig.set_chaos(down=True)
    for _ in range(5):
        assert rig.uploader.drain_once() is False
    assert rig.outbox.count() == 3       # nothing deleted while down
    assert rig.uploader.network_state in ("RETRYING", "DOWN")
    rig.set_chaos(down=False)
    assert _drain(rig)
    assert rig.stored() == 3
    assert rig.uploader.network_state == "OK"


def test_conflict_goes_to_dead_table(rig):
    rig.outbox.put(rig.batch(5, loud=-18.4))
    rig.uploader.drain_once()            # stored seq 5
    rig.outbox.put(rig.batch(5, loud=-30.0))  # same seq, different content
    rig.uploader.drain_once()
    assert rig.outbox.count() == 0
    assert rig.outbox.dead_count() == 1


def test_bad_signature_is_kept_not_dead(rig):
    bad = rig.batch(7)
    bad["peaks_b64"] = ("B" if bad["peaks_b64"][0] != "B" else "C") + bad["peaks_b64"][1:]
    rig.outbox.put(bad)
    rig.uploader.drain_once()
    assert rig.outbox.count() == 1       # kept for the operator
    assert rig.outbox.dead_count() == 0
    assert rig.outbox.peek(1)[0][2] == 1  # one attempt recorded


def test_bulk_used_when_queue_is_long(rig):
    for seq in range(1, 26):
        rig.outbox.put(rig.batch(seq))
    assert rig.uploader.drain_once() is True  # one bulk round takes up to 50
    assert rig.outbox.count() == 0
    assert rig.stored() == 25


def test_restart_resumes_from_disk(tmp_path):
    rig = Rig(tmp_path)
    for seq in range(1, 4):
        rig.outbox.put(rig.batch(seq))
    # simulate a crash: new objects, same disk, same server
    again = Uploader(Outbox(os.path.join(str(tmp_path), "M-96.db")), rig.client, CFG, rig.seed, sleep=lambda s: None)
    while again.outbox.count():
        again.drain_once()
    assert rig.stored() == 3


def test_heartbeat_is_signed_and_reports_skew(rig):
    for seq in range(1, 4):
        rig.outbox.put(rig.batch(seq))
    skew = rig.uploader.send_heartbeat()
    assert skew is not None
    assert abs(skew) < 5.0               # same machine, same clock
    assert rig.uploader.maybe_heartbeat(now=rig.uploader.last_heartbeat + 1) is None  # not due yet


def test_run_thread_stops_cleanly(rig):
    rig.outbox.put(rig.batch(1))
    stop = threading.Event()
    t = threading.Thread(target=rig.uploader.run, args=(stop,), daemon=True)
    t.start()
    for _ in range(200):
        if rig.outbox.count() == 0:
            break
        stop.wait(0.05)
    stop.set()
    t.join(timeout=5)
    assert not t.is_alive()
    assert rig.outbox.count() == 0
