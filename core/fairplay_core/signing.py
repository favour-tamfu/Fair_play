"""Ed25519 signing for meter messages (contract §3.2–§3.3).

A meter holds a 32-byte private *seed* (Laptop A: `device/secrets/<meter>.seed`, hex, gitignored).
SONACAM holds the public key (`contract/meters/<meter>.pub.json`). Every batch/heartbeat/calibration is signed over
`schema.canonical_bytes(dict)`, i.e. all fields except "sig".

Verification never raises: any malformed input (missing sig, bad base64, wrong key length) simply returns False,
so the ingest API can map it to 401 bad_signature.
"""
from __future__ import annotations

import base64
import binascii
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Union

from nacl.exceptions import BadSignatureError
from nacl.signing import SigningKey, VerifyKey

from .schema import METER_ID_RE, VENUE_ID_RE, canonical_bytes

SEED_BYTES = 32
PUB_BYTES = 32

Seed = Union[bytes, str]  # raw 32 bytes, or 64 hex characters


def _seed_bytes(seed: Seed) -> bytes:
    if isinstance(seed, str):
        try:
            seed = bytes.fromhex(seed.strip())
        except ValueError as e:
            raise ValueError("seed hex string is not valid hex") from e
    if len(seed) != SEED_BYTES:
        raise ValueError(f"seed must be {SEED_BYTES} bytes, got {len(seed)}")
    return seed


# ------------------------------------------------------------------ keys

def generate_seed() -> bytes:
    """New random 32-byte Ed25519 seed."""
    return bytes(SigningKey.generate())


def public_key_b64(seed: Seed) -> str:
    """Base64 of the 32-byte public key that belongs to this seed."""
    return base64.b64encode(bytes(SigningKey(_seed_bytes(seed)).verify_key)).decode("ascii")


# ------------------------------------------------------------------ sign / verify

def sign_bytes(seed: Seed, message: bytes) -> str:
    """Base64 Ed25519 signature (64 bytes) of raw bytes."""
    return base64.b64encode(SigningKey(_seed_bytes(seed)).sign(message).signature).decode("ascii")


def verify_bytes(pub_b64: str, message: bytes, sig_b64: str) -> bool:
    try:
        pub = base64.b64decode(pub_b64, validate=True)
        sig = base64.b64decode(sig_b64, validate=True)
        if len(pub) != PUB_BYTES or len(sig) != 64:
            return False
        VerifyKey(pub).verify(message, sig)
        return True
    except (BadSignatureError, binascii.Error, ValueError, TypeError):
        return False


def sign_dict(seed: Seed, d: dict[str, Any]) -> str:
    """Signature (base64) over canonical_bytes(d). Does not modify d; any existing "sig" is ignored."""
    return sign_bytes(seed, canonical_bytes(d))


def verify_dict(pub_b64: str, d: dict[str, Any]) -> bool:
    """True if d["sig"] is a valid signature of canonical_bytes(d) by this public key."""
    sig = d.get("sig")
    if not isinstance(sig, str):
        return False
    try:
        msg = canonical_bytes(d)
    except (TypeError, ValueError):
        return False
    return verify_bytes(pub_b64, msg, sig)


def sign_batch(seed: Seed, batch: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of the batch (or heartbeat/calibration) dict with "sig" set."""
    return {**batch, "sig": sign_dict(seed, batch)}


def verify_batch(pub_b64: str, batch: dict[str, Any]) -> bool:
    """Alias of verify_dict, named as used in docs/PLAN_A."""
    return verify_dict(pub_b64, batch)


# ------------------------------------------------------------------ key files

def save_seed(path: Union[str, Path], seed: Seed) -> None:
    """Write the seed as 64 hex characters (one line). Keep these files out of git."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(_seed_bytes(seed).hex() + "\n", encoding="ascii")


def load_seed(path: Union[str, Path]) -> bytes:
    return _seed_bytes(Path(path).read_text(encoding="ascii"))


def make_pub_record(meter_id: str, venue_id: str, seed: Seed, created_at: datetime | None = None) -> dict[str, str]:
    """The `<meter>.pub.json` content (contract §3.3)."""
    created = (created_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return {
        "meter_id": meter_id,
        "venue_id": venue_id,
        "public_key_b64": public_key_b64(seed),
        "created_at": created.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def validate_pub_record(rec: dict[str, Any]) -> dict[str, Any]:
    """Check a .pub.json dict; raise ValueError if malformed. Returns it unchanged."""
    for k in ("meter_id", "venue_id", "public_key_b64"):
        if not isinstance(rec.get(k), str):
            raise ValueError(f"pub record missing string field {k!r}")
    if not re.match(METER_ID_RE, rec["meter_id"]):
        raise ValueError(f"bad meter_id {rec['meter_id']!r}")
    if not re.match(VENUE_ID_RE, rec["venue_id"]):
        raise ValueError(f"bad venue_id {rec['venue_id']!r}")
    try:
        key = base64.b64decode(rec["public_key_b64"], validate=True)
    except binascii.Error as e:
        raise ValueError("public_key_b64 is not valid base64") from e
    if len(key) != PUB_BYTES:
        raise ValueError(f"public key must be {PUB_BYTES} bytes")
    return rec


def save_pub(path: Union[str, Path], rec: dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(validate_pub_record(rec), indent=2) + "\n", encoding="utf-8")


def load_pub(path: Union[str, Path]) -> dict[str, Any]:
    """Read and validate a `<meter>.pub.json` file."""
    return validate_pub_record(json.loads(Path(path).read_text(encoding="utf-8")))


__all__ = [
    "generate_seed", "public_key_b64", "sign_bytes", "verify_bytes", "sign_dict", "verify_dict",
    "sign_batch", "verify_batch", "save_seed", "load_seed", "make_pub_record", "validate_pub_record",
    "save_pub", "load_pub",
]
