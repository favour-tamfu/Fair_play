"""Tests for the event log, uploader logging, and the monitor's per-sequence state."""
import json
import os

from device.agent.eventlog import EventLog
from device.agent.outbox import Outbox
from device.agent.uploader import Uploader
from device.tests.test_uploader_faults import CFG, SEED, Server
from device.tools.monitor import build_state


def test_eventlog_appends_and_reads_back(tmp_path):
    log = EventLog(str(tmp_path / "e.jsonl"))
    log.append("window", seq=1, peaks=60)
    log.append("acked", seq=1)
    events = log.read()
    assert [e["event"] for e in events] == ["window", "acked"]
    assert events[0]["seq"] == 1 and "t" in events[0]


def test_uploader_logs_acks_and_parks(tmp_path):
    log = EventLog(str(tmp_path / "e.jsonl"))
    ob = Outbox(str(tmp_path / "o.db"))
    for s in (1, 2, 3):
        ob.put({"seq": s, "meter_id": "M-07", "sig": "x", "peaks_b64": ""})
    up = Uploader(ob, Server(refuse_single={2: 401}), CFG, SEED, sleep=lambda s: None, rand=lambda: 0.5, log=log.append)
    for _ in range(6):
        up.drain_once()
    kinds = {(e["event"], e.get("seq")) for e in log.read()}
    assert ("acked", 1) in kinds and ("acked", 3) in kinds
    assert ("parked", 2) in kinds


def test_monitor_flags_a_made_batch_that_was_never_acked(tmp_path):
    state_dir = str(tmp_path)
    log = EventLog(os.path.join(state_dir, "M-07_events.jsonl"))
    for s in (1, 2, 3):
        log.append("window", seq=s)
    log.append("acked", seq=1)
    log.append("acked", seq=3)            # seq 2: made, not acked, not in the outbox
    state = build_state("M-07", state_dir)
    status = {q["seq"]: q["status"] for q in state["seqs"]}
    assert status == {1: "acked", 2: "missing", 3: "acked"}
    assert state["missing"] == 1 and state["acked"] == 2


def test_monitor_shows_queued_batches_from_the_outbox(tmp_path):
    state_dir = str(tmp_path)
    log = EventLog(os.path.join(state_dir, "M-07_events.jsonl"))
    log.append("window", seq=1)
    log.append("window", seq=2)
    ob = Outbox(os.path.join(state_dir, "M-07_outbox.db"))
    ob.put({"seq": 2, "meter_id": "M-07", "sig": "x", "peaks_b64": ""})
    status = {q["seq"]: q["status"] for q in build_state("M-07", state_dir)["seqs"]}
    assert status == {1: "missing", 2: "queued"} or status[2] == "queued"
    json.dumps(build_state("M-07", state_dir))  # serialisable for the page
