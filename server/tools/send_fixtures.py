"""Send test batches to a running server, like a meter would (B-T03 DoD; no Laptop A needed).

    python -m server.tools.send_fixtures [--url http://localhost:8000] [--count 5] [--bulk]

1. registers the TEST meter M-90 (key from contract/fixtures/batches/tv_keys.json)
2. posts the contract test vectors (expect 200 stored|duplicate, 401, 422)
3. posts --count synthetic M-90 batches (seq 1000+, deterministic → re-runs answer "duplicate")
4. sends one heartbeat
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone

import httpx

from fairplay_core.schema import format_utc
from fairplay_core.signing import sign_batch
from server.tools.make_test_vectors import OUT, SEED, synthetic_peaks, unsigned_batch

T0 = datetime(2026, 11, 24, 20, 0, tzinfo=timezone.utc)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--count", type=int, default=5)
    ap.add_argument("--bulk", action="store_true", help="send the synthetic batches in one /v1/batches/bulk call")
    a = ap.parse_args(argv)
    keys = json.loads((OUT / "tv_keys.json").read_text(encoding="utf-8"))
    ok = True
    with httpx.Client(base_url=a.url, timeout=10) as c:
        r = c.post("/v1/meters/register", json={k: keys[k] for k in ("meter_id", "venue_id", "public_key_b64", "created_at")})
        print(f"register M-90            -> {r.status_code} {r.json()}")
        for name, expect in [("tv_batch_valid.json", {200}), ("tv_batch_badsig.json", {401}),
                             ("tv_batch_badversion.json", {422})]:
            r = c.post("/v1/batches", json=json.loads((OUT / name).read_text(encoding="utf-8")))
            good = r.status_code in expect
            ok &= good
            print(f"{name:24} -> {r.status_code} {r.json()}  {'OK' if good else 'UNEXPECTED'}")
        batches = [sign_batch(SEED, unsigned_batch(synthetic_peaks(seed=i), seq=1000 + i,
                                                   window_start=format_utc(T0 + timedelta(seconds=10 * i))))
                   for i in range(a.count)]
        if a.bulk:
            r = c.post("/v1/batches/bulk", json={"batches": batches})
            print(f"bulk x{a.count:<19} -> {r.status_code} {[x['status'] for x in r.json()['results']]}")
        else:
            for b in batches:
                r = c.post("/v1/batches", json=b)
                ok &= r.status_code == 200
                print(f"synthetic seq {b['seq']:<10} -> {r.status_code} {r.json()}")
        hb = sign_batch(SEED, {"meter_id": "M-90", "venue_id": "V-BUEA-CIMFEST",
                               "sent_at": format_utc(datetime.now(timezone.utc)), "queued": 0, "fw": "send_fixtures"})
        r = c.post("/v1/heartbeat", json=hb)
        print(f"heartbeat                -> {r.status_code} {r.json()}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
