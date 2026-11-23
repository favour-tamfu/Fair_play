"""MC0 helper for Laptop A (run by scripts/cp0_a.ps1).

1. Prints the golden SHA-256 of pack_peaks(extract_peaks(tone_mix.wav)) using the
   agreed WAV recipe (REQUESTS R-001), to compare with Laptop B.
2. Builds one batch signed with the real M-07 key (device/secrets/M-07.seed) from the
   same WAV, and writes it to data/cp0/batch_M07.json (git-ignored) for B's check_batch.

Run from the repo root with the venv active:  python scripts\cp0_a.py
"""
import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # run as a script: make the repo packages importable
sys.path.insert(0, str(ROOT / "core" / "tests"))  # reuse the one WAV loader used by test_peaks.py

from datetime import datetime, timezone  # noqa: E402

from test_peaks import TONE_WAV, load_wav_for_golden  # noqa: E402

from device.agent.batcher import sign_fields  # noqa: E402
from device.tools.provision import load_seed  # noqa: E402
from fairplay_core.constants import FP_VERSION, WINDOW_S  # noqa: E402
from fairplay_core.peaks import extract_peaks, pack_peaks, peaks_to_b64, rms_dbfs  # noqa: E402

METER = "M-07"
VENUE = "V-BUEA-CIMFEST"
CELL = "624-01-0412-01733"


def main() -> int:
    x8 = load_wav_for_golden(TONE_WAV)
    peaks = extract_peaks(x8)
    golden = hashlib.sha256(pack_peaks(peaks)).hexdigest()
    print(f"golden SHA tone_mix.wav: {golden}  ({peaks.size} peaks)")

    window = x8[: WINDOW_S * 8000]
    fields = {
        "v": 1,
        "fp_version": FP_VERSION,
        "meter_id": METER,
        "venue_id": VENUE,
        "seq": 1,
        "window_start": datetime(2026, 11, 23, 21, 14, tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "window_ms": 10000,
        "loudness_db": rms_dbfs(window),
        "cell_id": CELL,
        "fw": "agent-0.1.0",
        "n_peaks": int(peaks.size),
        "peaks_b64": peaks_to_b64(peaks),
    }
    seed = load_seed(METER)
    fields["sig"] = sign_fields(seed, dict(fields))

    out = ROOT / "data" / "cp0" / "batch_M07.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(fields, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote signed batch: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
