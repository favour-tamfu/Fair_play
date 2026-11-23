"""Tests for fairplay_core.schema (B-T01). Uses synthetic peaks only (no dependency on peaks.py)."""
import base64
import json
import struct
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from fairplay_core.schema import (
    Batch, Calibration, Heartbeat, canonical_bytes, decode_peak_records, format_utc, parse_utc,
)


def pack(records):
    return base64.b64encode(b"".join(struct.pack("<HBB", f, b, m) for f, b, m in records)).decode("ascii")


PEAKS = [(0, 7, 100), (12, 64, 180), (150, 128, 200), (310, 224, 255)]


def batch_dict(**over):
    d = {
        "v": 1, "fp_version": "fp-1.0", "meter_id": "M-07", "venue_id": "V-BUEA-CIMFEST", "seq": 1842,
        "window_start": "2026-11-24T21:14:00.000Z", "window_ms": 10000, "loudness_db": -18.4,
        "cell_id": "624-01-0412-01733", "fw": "agent-0.1.0", "n_peaks": len(PEAKS), "peaks_b64": pack(PEAKS),
        "sig": base64.b64encode(bytes(64)).decode(),
    }
    d.update(over)
    return d


# ---------------------------------------------------------------- valid input

def test_valid_batch_parses():
    b = Batch.model_validate(batch_dict())
    assert b.seq == 1842 and b.n_peaks == 4
    assert b.window_start_dt == datetime(2026, 11, 24, 21, 14, tzinfo=timezone.utc)
    recs = b.peak_records()
    assert recs["frame"].tolist() == [0, 12, 150, 310]
    assert recs["bin"].tolist() == [7, 64, 128, 224]


def test_empty_window_is_valid():
    b = Batch.model_validate(batch_dict(n_peaks=0, peaks_b64=""))
    assert b.n_peaks == 0


def test_unsigned_batch_can_be_built_and_has_no_sig_on_wire():
    d = batch_dict()
    del d["sig"]
    b = Batch.model_validate(d)
    assert "sig" not in b.to_wire()


def test_valid_batch_survives_json_roundtrip():
    d = batch_dict()
    assert Batch.model_validate(json.loads(json.dumps(d))).to_wire() == d


def test_loudness_rounded_to_1_decimal():
    assert Batch.model_validate(batch_dict(loudness_db=-18.437)).loudness_db == -18.4
    assert Batch.model_validate(batch_dict(loudness_db=-18)).loudness_db == -18.0  # int accepted for float


# ---------------------------------------------------------------- canonical bytes

def test_canonical_bytes_independent_of_key_order_and_excludes_sig():
    d = batch_dict()
    shuffled = dict(reversed(list(d.items())))
    assert canonical_bytes(d) == canonical_bytes(shuffled)
    assert b'"sig"' not in canonical_bytes(d)
    assert canonical_bytes(d) == canonical_bytes({**d, "sig": "something else"})


def test_canonical_bytes_exact_format():
    assert canonical_bytes({"b": 1, "a": "é", "sig": "x", "c": -18.4}) == '{"a":"é","b":1,"c":-18.4}'.encode("utf-8")


def test_model_canonical_bytes_equal_raw_canonical_bytes():
    d = batch_dict()
    assert Batch.model_validate(d).canonical_bytes() == canonical_bytes(d)


# ---------------------------------------------------------------- rejections

@pytest.mark.parametrize("over, why", [
    ({"fp_version": "fp-0.9"}, "fp_version"),
    ({"v": 2}, "v"),
    ({"seq": 0}, "seq"),
    ({"seq": "5"}, "strict: no str→int"),
    ({"window_ms": 5000}, "window_ms"),
    ({"window_start": "2026-11-24T21:14:00Z"}, "no milliseconds"),
    ({"window_start": "2026-11-24T21:14:00.000+01:00"}, "not Z"),
    ({"window_start": "2026-13-24T21:14:00.000Z"}, "impossible date"),
    ({"meter_id": "M7"}, "meter_id"),
    ({"meter_id": "M-12345"}, "meter_id too long"),
    ({"venue_id": "V-buea-cimfest"}, "venue_id lower case"),
    ({"loudness_db": 3.0}, "loudness > 0"),
    ({"loudness_db": -120.0}, "loudness < -100"),
    ({"cell_id": "x" * 33}, "cell_id too long"),
    ({"fw": "x" * 33}, "fw too long"),
    ({"n_peaks": 5}, "n_peaks mismatch"),
    ({"peaks_b64": "not base64!!", "n_peaks": 0}, "bad base64"),
    ({"peaks_b64": base64.b64encode(b"abc").decode(), "n_peaks": 0}, "not multiple of 4"),
    ({"peaks_b64": pack([(400, 64, 100)]), "n_peaks": 1}, "frame 400"),
    ({"peaks_b64": pack([(311, 64, 100)]), "n_peaks": 1}, "frame 311"),
    ({"peaks_b64": pack([(10, 6, 100)]), "n_peaks": 1}, "bin 6"),
    ({"peaks_b64": pack([(10, 225, 100)]), "n_peaks": 1}, "bin 225"),
    ({"sig": base64.b64encode(bytes(10)).decode()}, "sig wrong length"),
    ({"extra_field": 1}, "extra field"),
])
def test_batch_rejects(over, why):
    with pytest.raises(ValidationError):
        Batch.model_validate(batch_dict(**over))


def test_missing_required_field_rejected():
    d = batch_dict()
    del d["meter_id"]
    with pytest.raises(ValidationError):
        Batch.model_validate(d)


# ---------------------------------------------------------------- heartbeat + calibration

def test_heartbeat():
    hb = {"meter_id": "M-07", "venue_id": "V-BUEA-CIMFEST", "sent_at": "2026-11-24T21:14:00.000Z",
          "queued": 3, "fw": "agent-0.1.0"}
    assert Heartbeat.model_validate(hb).queued == 3
    with pytest.raises(ValidationError):
        Heartbeat.model_validate({**hb, "queued": -1})
    with pytest.raises(ValidationError):
        Heartbeat.model_validate({**hb, "sent_at": "yesterday"})


def test_calibration():
    cal = {"meter_id": "M-07", "run_id": "CAL-1", "started_at": "2026-11-24T17:30:00Z",
           "ended_at": "2026-11-24T17:34:00Z",
           "expected": [{"song_id": "S-000001", "played_at": "2026-11-24T17:30:05Z"},
                        {"song_id": "S-M0001", "played_at": "2026-11-24T17:31:05Z"}]}
    c = Calibration.model_validate(cal)
    assert len(c.expected) == 2
    with pytest.raises(ValidationError):
        Calibration.model_validate({**cal, "ended_at": "2026-11-24T17:00:00Z"})
    with pytest.raises(ValidationError):
        Calibration.model_validate({**cal, "expected": [{"song_id": "song1", "played_at": "2026-11-24T17:30:05Z"}]})
    with pytest.raises(ValidationError):
        Calibration.model_validate({**cal, "expected": []})


# ---------------------------------------------------------------- time helpers

def test_time_helpers_roundtrip():
    dt = datetime(2026, 11, 24, 21, 14, 0, 123456, tzinfo=timezone.utc)
    s = format_utc(dt)
    assert s == "2026-11-24T21:14:00.123Z"
    assert parse_utc(s) == dt.replace(microsecond=123000)


def test_decode_peak_records():
    recs = decode_peak_records(pack(PEAKS))
    assert recs.dtype.itemsize == 4 and len(recs) == 4
    assert recs["mag"].tolist() == [100, 180, 200, 255]
