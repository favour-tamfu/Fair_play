"""The committed batch test vectors (contract §3.4) behave as documented. Needs only fairplay_core + jsonschema,
so Laptop A can run it too."""
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from fairplay_core.schema import Batch
from fairplay_core.signing import public_key_b64, verify_batch

ROOT = Path(__file__).resolve().parents[2]
TV = ROOT / "contract" / "fixtures" / "batches"
BATCH_SCHEMA = Draft202012Validator(json.loads((ROOT / "contract/schemas/batch.schema.json").read_text("utf-8")))


def load(name):
    return json.loads((TV / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def pub():
    keys = load("tv_keys.json")
    assert public_key_b64(keys["seed_hex"]) == keys["public_key_b64"]  # seed and public key belong together
    return keys["public_key_b64"]


def test_valid_vector(pub):
    b = load("tv_batch_valid.json")
    assert BATCH_SCHEMA.is_valid(b)
    Batch.model_validate(b)
    assert verify_batch(pub, b)                       # → server 200 stored


def test_badsig_vector_is_well_formed_but_signature_fails(pub):
    b = load("tv_batch_badsig.json")
    assert BATCH_SCHEMA.is_valid(b)
    Batch.model_validate(b)                           # well-formed, so the server reaches the signature check
    assert not verify_batch(pub, b)                   # → server 401 bad_signature


def test_badversion_vector_is_signed_but_invalid(pub):
    b = load("tv_batch_badversion.json")
    assert verify_batch(pub, b)                       # signature fine…
    assert not BATCH_SCHEMA.is_valid(b)               # …but fp-0.9 → server 422 invalid
    with pytest.raises(ValidationError):
        Batch.model_validate(b)
