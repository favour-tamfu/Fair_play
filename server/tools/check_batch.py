"""Check a batch JSON file the way the server will: JSON Schema, pydantic model, signature.

    python -m server.tools.check_batch <batch.json> <pub.json | tv_keys.json>

Used at MC0 to verify a batch signed on Laptop A, and later to debug rejected batches.
Exit code 0 = valid and correctly signed.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from pydantic import ValidationError

from fairplay_core.schema import Batch
from fairplay_core.signing import validate_pub_record, verify_batch

SCHEMA = Path(__file__).resolve().parents[2] / "contract" / "schemas" / "batch.schema.json"


def check(batch: dict, pub: dict) -> list[str]:
    problems = []
    errs = sorted(Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8"))).iter_errors(batch),
                  key=lambda e: list(e.path))
    problems += [f"schema: {'/'.join(map(str, e.path)) or '(root)'}: {e.message}" for e in errs]
    try:
        Batch.model_validate(batch)
    except ValidationError as e:
        problems += [f"model: {'.'.join(map(str, x['loc'])) or '(root)'}: {x['msg']}" for x in e.errors()]
    validate_pub_record(pub)
    if batch.get("meter_id") != pub["meter_id"]:
        problems.append(f"meter: batch is from {batch.get('meter_id')}, key is for {pub['meter_id']}")
    if not verify_batch(pub["public_key_b64"], batch):
        problems.append("signature: does NOT verify with this public key")
    return problems


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    batch = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    pub = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    problems = check(batch, pub)
    if problems:
        print(f"INVALID {argv[0]}")
        for p in problems:
            print("  -", p)
        return 1
    print(f"OK {argv[0]}: meter {batch['meter_id']} seq {batch['seq']} n_peaks {batch['n_peaks']}, signature verified")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
