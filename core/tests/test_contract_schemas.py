"""contract/schemas/*.json are valid draft 2020-12 and agree with the pydantic models (B-T01)."""
import base64
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from fairplay_core.schema import Batch
from fairplay_core.signing import generate_seed, sign_batch
from test_schema import batch_dict, pack

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "contract" / "schemas"
REQUIRED = ["batch", "heartbeat", "calibration", "song_upload_response", "overview", "venues", "plays", "shares",
            "flags", "payouts", "compare_flat", "ledger_status", "artist"]  # contract §9
ALL = sorted(p.name[: -len(".schema.json")] for p in SCHEMA_DIR.glob("*.schema.json"))


def validator(name):
    return Draft202012Validator(json.loads((SCHEMA_DIR / f"{name}.schema.json").read_text(encoding="utf-8")))


def ok(name, instance):
    return validator(name).is_valid(instance)


def test_all_contract_schemas_exist():
    assert set(REQUIRED) <= set(ALL)


@pytest.mark.parametrize("name", ALL)
def test_schema_is_valid_draft_2020_12(name):
    doc = json.loads((SCHEMA_DIR / f"{name}.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(doc)
    assert doc["$schema"] == "https://json-schema.org/draft/2020-12/schema"


# ---------------------------------------------------------------- batch: JSON Schema ⇔ pydantic agree

def signed_batch(**over):
    d = batch_dict(**over)
    d.pop("sig")
    return sign_batch(generate_seed(), d)


def test_signed_batch_valid_in_both():
    b = signed_batch()
    assert ok("batch", b)
    Batch.model_validate(b)


@pytest.mark.parametrize("over", [
    {"fp_version": "fp-0.9"}, {"v": 2}, {"seq": 0}, {"seq": "5"}, {"window_ms": 5000},
    {"window_start": "2026-11-24T21:14:00Z"}, {"meter_id": "M7"}, {"venue_id": "V-buea-cimfest"},
    {"loudness_db": 3.0}, {"cell_id": "x" * 33}, {"peaks_b64": "not base64!!", "n_peaks": 0},
    {"extra_field": 1},
])
def test_bad_batch_rejected_by_both(over):
    b = {**signed_batch(), **over}
    assert not ok("batch", b)
    with pytest.raises(ValidationError):
        Batch.model_validate(b)


def test_unsigned_batch_rejected_on_the_wire():
    b = signed_batch()
    del b["sig"]
    assert not ok("batch", b)


def test_heartbeat_and_calibration_signed_are_valid():
    seed = generate_seed()
    hb = sign_batch(seed, {"meter_id": "M-07", "venue_id": "V-BUEA-CIMFEST", "sent_at": "2026-11-24T21:14:00.000Z",
                           "queued": 2, "fw": "agent-0.1.0"})
    cal = sign_batch(seed, {"meter_id": "M-07", "run_id": "CAL-1", "started_at": "2026-11-24T17:30:00Z",
                            "ended_at": "2026-11-24T17:34:00Z",
                            "expected": [{"song_id": "S-000001", "played_at": "2026-11-24T17:30:05Z"}]})
    assert ok("heartbeat", hb) and ok("calibration", cal)
    assert not ok("calibration", {**cal, "expected": []})


# ---------------------------------------------------------------- read API: early-state shapes are valid

def test_empty_but_valid_shapes():
    assert ok("shares", {"stats_run_id": None, "rule_version": "sr-1.0", "pot_fcfa": 100_000_000,
                         "escrow_share": 0, "rows": []})
    assert ok("ledger_status", {"intact": True, "broken_at_play_id": None, "plays_checked": 0,
                                "last_root": None, "last_anchor": None})
    assert ok("overview", {"meters_online": 0, "meters_total": 1, "venues": 1, "plays_raw": 0, "plays_counted": 0,
                           "songs_ready": 0, "unidentified_music_min": 0, "rule_version": "sr-1.0",
                           "ledger_intact": True, "last_anchor": None})
    assert ok("payouts", {"pot_fcfa": 100_000_000, "frozen": False, "rows": [], "total_fcfa": 0})


def test_play_row_and_typo_detection():
    play = {"play_id": "P-3f2a9c1b7d4e", "venue_id": "V-BUEA-CIMFEST", "meter_id": "M-07", "song_id": "S-000001",
            "title": "Demo", "artist_name": "Artist", "started_at": "2026-11-24T21:14:00Z", "duration_s": 212.0,
            "source": "live", "weight": 1, "reasons": ["streak_1"]}
    assert ok("plays", [play])
    assert ok("plays", [{**play, "weight": None, "reasons": []}])
    assert not ok("plays", [{**play, "source": "radio"}])
    renamed = {("artist" if k == "artist_name" else k): v for k, v in play.items()}
    assert not ok("plays", [renamed])           # misspelt/renamed field → rejected


def test_compare_flat_uses_renamed_field():
    body = {"pot_fcfa": 100_000_000, "n_artists": 120, "flat_each_fcfa": 833_333, "misallocated_flat_fcfa": 1,
            "misallocated_fairplay_fcfa": 1, "basis": "mock_month_truth"}
    assert ok("compare_flat", body)
    old = {**{k: v for k, v in body.items() if k != "misallocated_fairplay_fcfa"}, "misallocated_soundproof_fcfa": 1}
    assert not ok("compare_flat", old)
