"""Tests for batch building, signing and sequence state (A-T03)."""
import base64
import json
import os

import nacl.signing
import numpy as np
import pytest

from device.agent.batcher import build_batch, canonical_bytes, format_window_start, verify_fields
from device.agent.state import MeterState
from fairplay_core.peaks import extract_peaks

CFG = {"meter_id": "M-99", "venue_id": "V-TEST-ABC123", "cell_id": "624-01-0412-01733", "fw": "agent-test"}
SCHEMA = os.path.join("contract", "schemas", "batch.schema.json")


@pytest.fixture
def keypair():
    key = nacl.signing.SigningKey.generate()
    return bytes(key), base64.b64encode(bytes(key.verify_key)).decode("ascii")


@pytest.fixture
def peaks():
    t = np.arange(80_000) / 8_000
    x8 = (0.5 * np.sin(2 * np.pi * 1000 * t)).astype(np.float32)
    return extract_peaks(x8)


def test_signature_verifies_and_tampering_fails(keypair, peaks):
    seed, pub = keypair
    batch = build_batch(CFG, seq=1, window_start_utc=1_763_910_840.0, peaks=peaks, loudness_db=-18.44, seed=seed)
    assert verify_fields(pub, batch)

    bad = dict(batch)
    chars = list(bad["peaks_b64"])
    chars[0] = "B" if chars[0] != "B" else "C"  # change one character
    bad["peaks_b64"] = "".join(chars)
    assert not verify_fields(pub, bad)


def test_signature_rejects_a_different_key(keypair, peaks):
    seed, _ = keypair
    other = base64.b64encode(bytes(nacl.signing.SigningKey.generate().verify_key)).decode("ascii")
    batch = build_batch(CFG, seq=1, window_start_utc=1_763_910_840.0, peaks=peaks, loudness_db=-18.4, seed=seed)
    assert not verify_fields(other, batch)


def test_fields_follow_contract(keypair, peaks):
    seed, _ = keypair
    batch = build_batch(CFG, seq=7, window_start_utc=1_763_910_840.5, peaks=peaks, loudness_db=-18.44, seed=seed)
    assert batch["v"] == 1
    assert batch["fp_version"] == "fp-1.0"
    assert batch["window_ms"] == 10_000
    assert batch["loudness_db"] == -18.4  # rounded to 1 decimal before signing
    assert batch["n_peaks"] == peaks.size
    assert batch["window_start"] == format_window_start(1_763_910_840.5)
    assert batch["window_start"].endswith("Z") and "." in batch["window_start"]
    assert len(base64.b64decode(batch["peaks_b64"])) == 4 * peaks.size


def test_canonical_bytes_exclude_sig_and_are_sorted():
    raw = canonical_bytes({"b": 1, "a": "x", "sig": "zzz"})
    assert raw == b'{"a":"x","b":1}'


def test_seq_survives_restart(tmp_path):
    state = MeterState("M-99", state_dir=str(tmp_path))
    assert state.next_seq() == 1
    assert state.next_seq() == 2
    restarted = MeterState("M-99", state_dir=str(tmp_path))
    assert restarted.last_seq() == 2
    assert restarted.next_seq() == 3


def test_batch_validates_against_schema_when_available(keypair, peaks):
    jsonschema = pytest.importorskip("jsonschema")
    if not os.path.exists(SCHEMA):
        pytest.skip("contract/schemas/batch.schema.json not in repo yet (B-T01)")
    seed, _ = keypair
    batch = build_batch(CFG, seq=1, window_start_utc=1_763_910_840.0, peaks=peaks, loudness_db=-18.4, seed=seed)
    with open(SCHEMA, encoding="utf-8") as fh:
        schema = json.load(fh)
    jsonschema.validate(batch, schema)
