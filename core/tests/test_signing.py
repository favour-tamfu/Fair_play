"""Tests for fairplay_core.signing (B-T01)."""
import base64
import json
import struct
from datetime import datetime, timezone

import pytest

from fairplay_core.schema import Batch
from fairplay_core.signing import (
    generate_seed, load_pub, load_seed, make_pub_record, public_key_b64, save_pub, save_seed, sign_batch,
    sign_bytes, sign_dict, verify_batch, verify_bytes, verify_dict,
)

# RFC 8032 §7.1, TEST 1 (empty message) — proves we produce standard Ed25519
RFC_SEED = "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60"
RFC_PUB = "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"
RFC_SIG = ("e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155"
           "5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b")


def b64hex(h):
    return base64.b64encode(bytes.fromhex(h)).decode()


def make_batch(seq=1):
    peaks = b"".join(struct.pack("<HBB", f, b, m) for f, b, m in [(3, 40, 120), (90, 100, 200), (300, 200, 150)])
    return {"v": 1, "fp_version": "fp-1.0", "meter_id": "M-07", "venue_id": "V-BUEA-CIMFEST", "seq": seq,
            "window_start": "2026-11-24T21:14:00.000Z", "window_ms": 10000, "loudness_db": -18.4,
            "cell_id": "624-01-0412-01733", "fw": "agent-0.1.0", "n_peaks": 3,
            "peaks_b64": base64.b64encode(peaks).decode()}


@pytest.fixture
def seed():
    return generate_seed()


def test_rfc8032_vector():
    assert public_key_b64(RFC_SEED) == b64hex(RFC_PUB)
    assert sign_bytes(RFC_SEED, b"") == b64hex(RFC_SIG)
    assert verify_bytes(b64hex(RFC_PUB), b"", b64hex(RFC_SIG))


def test_seed_is_32_random_bytes():
    a, b = generate_seed(), generate_seed()
    assert len(a) == 32 and a != b


def test_sign_verify_roundtrip(seed):
    signed = sign_batch(seed, make_batch())
    assert verify_batch(public_key_b64(seed), signed)
    Batch.model_validate(signed)  # signed batch is still a valid Batch (sig is 64 bytes)


def test_sign_batch_does_not_mutate_input(seed):
    b = make_batch()
    sign_batch(seed, b)
    assert "sig" not in b


def test_signature_independent_of_key_order(seed):
    b = make_batch()
    sig = sign_dict(seed, b)
    shuffled = dict(reversed(list(b.items())))
    assert sign_dict(seed, shuffled) == sig            # Ed25519 is deterministic
    assert verify_dict(public_key_b64(seed), {**shuffled, "sig": sig})


def test_survives_json_wire_roundtrip(seed):
    signed = sign_batch(seed, make_batch())
    received = json.loads(json.dumps(signed))
    assert verify_dict(public_key_b64(seed), received)


def test_tampered_peaks_fail(seed):
    signed = sign_batch(seed, make_batch())
    p = signed["peaks_b64"]
    signed["peaks_b64"] = ("B" if p[0] != "B" else "C") + p[1:]
    assert not verify_dict(public_key_b64(seed), signed)


@pytest.mark.parametrize("field, value", [("seq", 2), ("loudness_db", -18.5), ("venue_id", "V-DLA-AKWA01"),
                                          ("window_start", "2026-11-24T21:14:10.000Z")])
def test_any_changed_field_fails(seed, field, value):
    signed = sign_batch(seed, make_batch())
    signed[field] = value
    assert not verify_dict(public_key_b64(seed), signed)


def test_added_field_fails(seed):
    signed = sign_batch(seed, make_batch())
    signed["bonus"] = 1
    assert not verify_dict(public_key_b64(seed), signed)


def test_wrong_key_fails(seed):
    signed = sign_batch(seed, make_batch())
    assert not verify_dict(public_key_b64(generate_seed()), signed)


@pytest.mark.parametrize("bad", [
    {"sig": None}, {"sig": 123}, {"sig": "not base64!!"}, {"sig": base64.b64encode(b"short").decode()},
])
def test_malformed_sig_returns_false(seed, bad):
    assert not verify_dict(public_key_b64(seed), {**make_batch(), **bad})


def test_missing_sig_returns_false(seed):
    assert not verify_dict(public_key_b64(seed), make_batch())


@pytest.mark.parametrize("pub", ["", "not base64!!", base64.b64encode(b"x" * 31).decode()])
def test_malformed_pub_returns_false(seed, pub):
    assert not verify_dict(pub, sign_batch(seed, make_batch()))


def test_bad_seed_rejected():
    with pytest.raises(ValueError):
        public_key_b64(b"x" * 31)
    with pytest.raises(ValueError):
        public_key_b64("zz" * 32)


def test_seed_file_roundtrip(tmp_path, seed):
    path = tmp_path / "secrets" / "M-07.seed"
    save_seed(path, seed)
    assert len(path.read_text().strip()) == 64
    assert load_seed(path) == seed


def test_pub_file_roundtrip_and_verify(tmp_path, seed):
    rec = make_pub_record("M-07", "V-BUEA-CIMFEST", seed, datetime(2026, 11, 23, 14, 30, tzinfo=timezone.utc))
    assert rec["created_at"] == "2026-11-23T14:30:00Z"
    path = tmp_path / "M-07.pub.json"
    save_pub(path, rec)
    loaded = load_pub(path)
    assert loaded == rec
    assert verify_batch(loaded["public_key_b64"], sign_batch(seed, make_batch()))


@pytest.mark.parametrize("over", [{"meter_id": "M7"}, {"venue_id": "bad"}, {"public_key_b64": "AAAA"}])
def test_bad_pub_file_rejected(tmp_path, seed, over):
    rec = {**make_pub_record("M-07", "V-BUEA-CIMFEST", seed), **over}
    path = tmp_path / "bad.pub.json"
    path.write_text(json.dumps(rec))
    with pytest.raises(ValueError):
        load_pub(path)


def test_heartbeat_signed_the_same_way(seed):
    hb = {"meter_id": "M-07", "venue_id": "V-BUEA-CIMFEST", "sent_at": "2026-11-24T21:14:00.000Z",
          "queued": 0, "fw": "agent-0.1.0"}
    assert verify_dict(public_key_b64(seed), sign_batch(seed, hb))
