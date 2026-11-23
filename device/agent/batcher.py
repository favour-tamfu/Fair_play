"""Batch builder and signer (A-T03), following contract 01 §3.

A batch is one 10 s window's peaks plus metadata, signed with the meter's Ed25519 key.
The canonical bytes are defined in contract §3.2. This module is the device-side copy of
that rule; once B's core.signing lands, both must produce identical bytes (MC0 check).
"""
import base64
import json
from datetime import datetime, timezone

import nacl.exceptions
import nacl.signing
import numpy as np

from fairplay_core.constants import FP_VERSION, SCHEMA_VERSION, WINDOW_S
from fairplay_core.peaks import peaks_to_b64


def format_window_start(epoch_s: float) -> str:
    """RFC 3339 UTC with milliseconds and a trailing Z."""
    dt = datetime.fromtimestamp(epoch_s, tz=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def canonical_bytes(fields: dict) -> bytes:
    """Contract §3.2: JSON of all fields except 'sig', sorted keys, no spaces, UTF-8."""
    body = {k: v for k, v in fields.items() if k != "sig"}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sign_fields(seed: bytes, fields: dict) -> str:
    signed = nacl.signing.SigningKey(seed).sign(canonical_bytes(fields)).signature
    return base64.b64encode(signed).decode("ascii")


def verify_fields(public_key_b64: str, obj: dict) -> bool:
    """True if obj['sig'] is a valid Ed25519 signature over its canonical bytes."""
    try:
        key = nacl.signing.VerifyKey(base64.b64decode(public_key_b64))
        key.verify(canonical_bytes(obj), base64.b64decode(obj["sig"]))
        return True
    except (nacl.exceptions.BadSignatureError, KeyError, ValueError):
        return False


def build_batch(cfg: dict, seq: int, window_start_utc: float, peaks: np.ndarray, loudness_db: float, seed: bytes) -> dict:
    """Build and sign one batch. cfg is the parsed meter TOML (device/config/<meter>.toml)."""
    if peaks.size and int(peaks["frame"].max()) >= 311:
        raise ValueError("window has frames beyond 310; not a 10 s window")
    fields = {
        "v": SCHEMA_VERSION,
        "fp_version": FP_VERSION,
        "meter_id": cfg["meter_id"],
        "venue_id": cfg["venue_id"],
        "seq": int(seq),
        "window_start": format_window_start(window_start_utc),
        "window_ms": WINDOW_S * 1000,
        "loudness_db": round(float(loudness_db), 1),
        "cell_id": cfg.get("cell_id", "")[:32],
        "fw": cfg.get("fw", "agent-0.1.0")[:32],
        "n_peaks": int(peaks.size),
        "peaks_b64": peaks_to_b64(peaks),
    }
    fields["sig"] = sign_fields(seed, fields)
    return fields


def _selftest() -> int:
    import tomllib

    from device.tools.provision import load_seed

    cfg_path = "device/config/M-07.toml"
    with open(cfg_path, "rb") as fh:
        cfg = tomllib.load(fh)
    seed = load_seed(cfg["meter_id"])
    from fairplay_core.peaks import extract_peaks

    t = np.arange(80_000) / 8_000
    x8 = (0.5 * np.sin(2 * np.pi * 1000 * t)).astype(np.float32)
    peaks = extract_peaks(x8)
    from datetime import datetime as _dt

    window_start = _dt(2026, 11, 23, 15, 0, tzinfo=timezone.utc).timestamp()
    batch = build_batch(cfg, seq=1, window_start_utc=window_start, peaks=peaks, loudness_db=-18.4, seed=seed)
    with open(f"contract/meters/{cfg['meter_id']}.pub.json", "r", encoding="utf-8") as fh:
        pub = json.load(fh)["public_key_b64"]
    print(json.dumps(batch, indent=2)[:800] + "\n  ...")
    print("signature verifies:", verify_fields(pub, batch))
    return 0 if verify_fields(pub, batch) else 1


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    raise SystemExit("use --selftest")
