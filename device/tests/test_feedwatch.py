"""Tests for the feed watcher's SSE parser and the monitor's match reader."""
import json

from device.tools.feedwatch import parse_sse
from device.tools.monitor import read_matches


SAMPLE = [
    ": ping - 2026-11-24 05:09:41",
    "",
    "event: meter",
    'data: {"meter_id": "M-07", "online": true}',
    "",
    "event: match",
    'data: {"meter_id": "M-07", "song_id": "S-000009", "title": "Ms. Jackson", "offset_s": 53.5, "confidence": 0.23, "accepted": true}',
    "",
    "event: match",
    'data: {"meter_id": "M-07", "song_id": null, "accepted": false}',
    "",
]


def test_parse_sse_gives_event_name_and_json_data():
    got = list(parse_sse(SAMPLE))
    assert [k for k, _ in got] == ["meter", "match", "match"]
    assert got[1][1]["title"] == "Ms. Jackson"
    assert got[2][1]["accepted"] is False


def test_parse_sse_skips_bad_json_and_comments():
    got = list(parse_sse(["event: match", "data: {not json", ""]))
    assert got == []


def test_read_matches_counts_accepted_and_rejected(tmp_path):
    path = tmp_path / "M-07_feed.jsonl"
    rows = [
        {"t": "t1", "kind": "match", "meter_id": "M-07", "accepted": True, "title": "A", "offset_s": 1.0},
        {"t": "t2", "kind": "match", "meter_id": "M-07", "accepted": False, "title": None},
        {"t": "t3", "kind": "batch", "meter_id": "M-07", "seq": 9},
        {"t": "t4", "kind": "match", "meter_id": "M-99", "accepted": True, "title": "other meter"},
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    m = read_matches("M-07", str(tmp_path))
    assert m["accepted"] == 1 and m["rejected"] == 1
    assert m["recent"][0]["t"] == "t2"   # newest first


def test_read_matches_with_no_file(tmp_path):
    assert read_matches("M-07", str(tmp_path)) == {"accepted": 0, "rejected": 0, "recent": []}

def test_seq_is_linked_to_its_match_by_window_start(tmp_path):
    from device.agent.eventlog import EventLog
    from device.tools.monitor import build_state
    ws1, ws2 = "2026-11-24T10:00:00.000Z", "2026-11-24T10:00:10.000Z"
    ev = EventLog(str(tmp_path / "M-07_events.jsonl"))
    ev.append("window", seq=1, window_start=ws1)
    ev.append("window", seq=2, window_start=ws2)
    ev.append("acked", seq=1)
    ev.append("acked", seq=2)
    feed = tmp_path / "M-07_feed.jsonl"
    feed.write_text(json.dumps({"t": "x", "kind": "match", "meter_id": "M-07", "window_start": ws1,
                                "accepted": True, "title": "Song A"}) + "\n", encoding="utf-8")
    seqs = {q["seq"]: q for q in build_state("M-07", str(tmp_path))["seqs"]}
    assert seqs[1]["match"] == "accepted" and seqs[1]["song"] == "Song A"
    assert seqs[2]["match"] == "none"
