"""Tests for the fake SONACAM (A-T04): contract §4 behaviour."""
import base64
import copy
import json

import nacl.signing
import numpy as np
import pytest
from fastapi.testclient import TestClient

from device.agent.batcher import build_batch, sign_fields
from device.tools.fake_sonacam import create_app
from fairplay_core.peaks import extract_peaks

CFG = {"meter_id": "M-98", "venue_id": "V-TEST-ABC123", "cell_id": "624-01-0412-01733", "fw": "agent-test"}


@pytest.fixture
def world():
    key = nacl.signing.SigningKey.generate()
    pub = base64.b64encode(bytes(key.verify_key)).decode("ascii")
    client = TestClient(create_app({"M-98": pub}))
    t = np.arange(80_000) / 8_000
    peaks = extract_peaks((0.5 * np.sin(2 * np.pi * 1000 * t)).astype(np.float32))
    return {"key": bytes(key), "client": client, "peaks": peaks}


def _tamper(peaks_b64: str) -> str:
    """Change the first character so the payload no longer matches its signature."""
    return ("B" if peaks_b64[0] != "B" else "C") + peaks_b64[1:]


def _batch(w, seq=1, loud=-18.4, cfg=CFG):
    return build_batch(cfg, seq=seq, window_start_utc=1_790_000_000.0, peaks=w["peaks"], loudness_db=loud, seed=w["key"])


def test_stored_then_duplicate(world):
    c = world["client"]
    b = _batch(world, seq=1)
    assert c.post("/v1/batches", json=b).json() == {"ack": 1, "status": "stored"}
    assert c.post("/v1/batches", json=b).json() == {"ack": 1, "status": "duplicate"}


def test_seq_conflict_when_same_seq_different_content(world):
    c = world["client"]
    c.post("/v1/batches", json=_batch(world, seq=2, loud=-18.4))
    r = c.post("/v1/batches", json=_batch(world, seq=2, loud=-30.0))
    assert r.status_code == 409
    assert r.json() == {"error": "seq_conflict"}


def test_bad_signature_is_401(world):
    c = world["client"]
    b = _batch(world, seq=3)
    b["peaks_b64"] = _tamper(b["peaks_b64"])
    r = c.post("/v1/batches", json=b)
    assert r.status_code == 401
    assert r.json() == {"error": "bad_signature"}


def test_unknown_meter_is_404(world):
    c = world["client"]
    b = _batch(world, seq=4, cfg={**CFG, "meter_id": "M-55"})
    r = c.post("/v1/batches", json=b)
    assert r.status_code == 404
    assert r.json() == {"error": "unknown_meter"}


def test_bad_fp_version_is_422(world):
    c = world["client"]
    b = _batch(world, seq=5)
    b["fp_version"] = "fp-0.9"
    b["sig"] = sign_fields(world["key"], b)  # validly signed, still rejected
    r = c.post("/v1/batches", json=b)
    assert r.status_code == 422
    assert r.json()["error"] == "invalid"


def test_missing_field_is_422(world):
    c = world["client"]
    b = _batch(world, seq=6)
    del b["window_ms"]
    assert c.post("/v1/batches", json=b).status_code == 422


def test_bulk_results_per_item(world):
    c = world["client"]
    good = _batch(world, seq=10)
    bad = copy.deepcopy(_batch(world, seq=11))
    bad["peaks_b64"] = _tamper(bad["peaks_b64"])
    r = c.post("/v1/batches/bulk", json={"batches": [good, bad, good]})
    assert r.status_code == 200
    statuses = [x["status"] for x in r.json()["results"]]
    assert statuses == ["stored", "error", "duplicate"]
    assert r.json()["results"][1]["error"] == "bad_signature"


def test_bulk_over_50_is_rejected(world):
    c = world["client"]
    items = [_batch(world, seq=100 + i) for i in range(51)]
    assert c.post("/v1/batches/bulk", json={"batches": items}).status_code == 422


def test_heartbeat_ok_and_bad_signature(world):
    c = world["client"]
    hb = {"meter_id": "M-98", "venue_id": "V-TEST-ABC123", "sent_at": "2026-11-23T21:00:00.000Z",
          "queued": 0, "fw": "agent-test"}
    hb["sig"] = sign_fields(world["key"], hb)
    r = c.post("/v1/heartbeat", json=hb)
    assert r.status_code == 200 and r.json()["ok"] is True and r.json()["server_time"].endswith("Z")
    hb["queued"] = 5  # change after signing
    assert c.post("/v1/heartbeat", json=hb).status_code == 401


def test_chaos_down_and_fail_rate(world):
    c = world["client"]
    c.post("/_chaos", json={"down": True})
    assert c.post("/v1/batches", json=_batch(world, seq=20)).status_code == 503
    c.post("/_chaos", json={"down": False, "fail_rate": 1.0})
    assert c.post("/v1/batches", json=_batch(world, seq=21)).status_code == 500
    c.post("/_chaos", json={"fail_rate": 0.0})
    assert c.post("/v1/batches", json=_batch(world, seq=22)).status_code == 200


def test_health_has_server_time(world):
    r = world["client"].get("/health")
    assert r.json()["ok"] is True and r.json()["server_time"].endswith("Z")
