"""Wire formats between the meter (Laptop A) and SONACAM (Laptop B) — contract §3 and §4.

- `Batch`: one 10-second window of peaks plus metadata, signed by the meter.
- `Heartbeat`, `Calibration`: the other signed device messages.
- `canonical_bytes(d)`: the exact bytes that get signed (contract §3.2).

Signature rule: the server verifies the signature over the dict exactly as received (`canonical_bytes(raw)`),
not over a re-serialised model. The device signs `canonical_bytes(batch.signable())` after building a `Batch`,
so both sides hash identical bytes.
"""
from __future__ import annotations

import base64
import binascii
import json
import re
from datetime import datetime, timezone
from typing import Any, Literal, Optional

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .constants import BIN_MAX, BIN_MIN, FP_VERSION, FRAMES_PER_WINDOW, SCHEMA_VERSION, WINDOW_S

METER_ID_RE = r"^M-[0-9]{2,4}$"
VENUE_ID_RE = r"^V-[A-Z]{3,10}-[A-Z0-9]{3,12}$"
SONG_ID_RE = r"^S-(?:[0-9]{6}|M[0-9]{4})$"
# RFC 3339 UTC with exactly 3 fractional digits and a literal Z, e.g. 2026-11-24T21:14:00.000Z
TS_MS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")
# Looser form for heartbeat/calibration times: optional fraction, Z required
TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$")

WINDOW_MS = WINDOW_S * 1000          # 10000
MAX_FRAME = FRAMES_PER_WINDOW - 1    # 310
PEAK_RECORD = np.dtype([("frame", "<u2"), ("bin", "u1"), ("mag", "u1")])  # <HBB, 4 bytes
SIG_BYTES = 64                       # Ed25519 signature length


# --------------------------------------------------------------------------- helpers

def canonical_bytes(d: dict[str, Any]) -> bytes:
    """Bytes to sign/verify: every field except "sig", sorted keys, no spaces, UTF-8 (contract §3.2)."""
    body = {k: v for k, v in d.items() if k != "sig"}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def format_utc(dt: datetime) -> str:
    """datetime → '2026-11-24T21:14:00.000Z' (UTC, milliseconds). Naive datetimes are treated as UTC."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def parse_utc(s: str) -> datetime:
    """'...Z' timestamp → timezone-aware UTC datetime."""
    if not TS_RE.match(s):
        raise ValueError(f"not an RFC 3339 UTC timestamp ending in Z: {s!r}")
    return datetime.fromisoformat(s[:-1]).replace(tzinfo=timezone.utc)


def _b64decode_strict(s: str, what: str) -> bytes:
    try:
        return base64.b64decode(s, validate=True)
    except (binascii.Error, ValueError) as e:
        raise ValueError(f"{what} is not valid padded standard base64") from e


def decode_peak_records(peaks_b64: str) -> np.ndarray:
    """Decode the wire peaks (n × <HBB) into a structured array (frame, bin, mag)."""
    raw = _b64decode_strict(peaks_b64, "peaks_b64")
    if len(raw) % PEAK_RECORD.itemsize:
        raise ValueError("peaks_b64 length is not a multiple of 4 bytes")
    return np.frombuffer(raw, dtype=PEAK_RECORD)


# --------------------------------------------------------------------------- models

class _Signed(BaseModel):
    # strict: no silent coercion ("5" → 5 would change the signed bytes); forbid: no smuggled extra fields
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    sig: Optional[str] = None  # absent while building; required by the server (verification fails without it)

    @field_validator("sig")
    @classmethod
    def _sig_shape(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and len(_b64decode_strict(v, "sig")) != SIG_BYTES:
            raise ValueError(f"sig must decode to {SIG_BYTES} bytes")
        return v

    def signable(self) -> dict[str, Any]:
        """The dict the signature covers (all fields except sig)."""
        return self.model_dump(exclude={"sig"})

    def canonical_bytes(self) -> bytes:
        return canonical_bytes(self.signable())

    def to_wire(self) -> dict[str, Any]:
        """Dict ready to send as JSON (sig omitted if not yet signed)."""
        return self.model_dump(exclude_none=True)


class Batch(_Signed):
    """One analysed 10 s window (contract §3.1)."""

    v: Literal[1]
    fp_version: str
    meter_id: str = Field(pattern=METER_ID_RE)
    venue_id: str = Field(pattern=VENUE_ID_RE)
    seq: int = Field(ge=1)
    window_start: str
    window_ms: int
    loudness_db: float = Field(ge=-100.0, le=0.0)
    cell_id: str = Field(max_length=32)
    fw: str = Field(max_length=32)
    n_peaks: int = Field(ge=0)
    peaks_b64: str

    @field_validator("fp_version")
    @classmethod
    def _fp_version(cls, v: str) -> str:
        if v != FP_VERSION:
            raise ValueError(f"fp_version must be {FP_VERSION!r}, got {v!r}")
        return v

    @field_validator("window_start")
    @classmethod
    def _window_start(cls, v: str) -> str:
        if not TS_MS_RE.match(v):
            raise ValueError("window_start must look like 2026-11-24T21:14:00.000Z (UTC, milliseconds, Z)")
        parse_utc(v)  # rejects impossible dates such as month 13
        return v

    @field_validator("window_ms")
    @classmethod
    def _window_ms(cls, v: int) -> int:
        if v != WINDOW_MS:
            raise ValueError(f"window_ms must be {WINDOW_MS}")
        return v

    @field_validator("loudness_db")
    @classmethod
    def _loudness_1dp(cls, v: float) -> float:
        return round(float(v), 1)

    @model_validator(mode="after")
    def _peaks_consistent(self) -> "Batch":
        recs = decode_peak_records(self.peaks_b64)
        if len(recs) != self.n_peaks:
            raise ValueError(f"n_peaks={self.n_peaks} but peaks_b64 holds {len(recs)} records")
        if len(recs):
            if int(recs["frame"].max()) > MAX_FRAME:
                raise ValueError(f"peak frame > {MAX_FRAME}")
            if int(recs["bin"].min()) < BIN_MIN or int(recs["bin"].max()) > BIN_MAX:
                raise ValueError(f"peak bin outside {BIN_MIN}..{BIN_MAX}")
        return self

    @property
    def window_start_dt(self) -> datetime:
        return parse_utc(self.window_start)

    def peak_records(self) -> np.ndarray:
        return decode_peak_records(self.peaks_b64)


class Heartbeat(_Signed):
    """Meter is alive; `queued` = batches waiting in its outbox (contract §4)."""

    meter_id: str = Field(pattern=METER_ID_RE)
    venue_id: str = Field(pattern=VENUE_ID_RE)
    sent_at: str
    queued: int = Field(ge=0)
    fw: str = Field(max_length=32)

    @field_validator("sent_at")
    @classmethod
    def _ts(cls, v: str) -> str:
        parse_utc(v)
        return v


class ExpectedPlay(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    song_id: str = Field(pattern=SONG_ID_RE)
    played_at: str

    @field_validator("played_at")
    @classmethod
    def _ts(cls, v: str) -> str:
        parse_utc(v)
        return v


class Calibration(_Signed):
    """Known songs played near a meter, used by B to compute its catch rate (contract §4)."""

    meter_id: str = Field(pattern=METER_ID_RE)
    run_id: str = Field(min_length=1, max_length=64)
    started_at: str
    ended_at: str
    expected: list[ExpectedPlay] = Field(min_length=1)

    @field_validator("started_at", "ended_at")
    @classmethod
    def _ts(cls, v: str) -> str:
        parse_utc(v)
        return v

    @model_validator(mode="after")
    def _order(self) -> "Calibration":
        if parse_utc(self.ended_at) < parse_utc(self.started_at):
            raise ValueError("ended_at is before started_at")
        return self


__all__ = [
    "Batch", "Heartbeat", "Calibration", "ExpectedPlay",
    "canonical_bytes", "format_utc", "parse_utc", "decode_peak_records",
    "PEAK_RECORD", "WINDOW_MS", "MAX_FRAME", "SCHEMA_VERSION",
]
