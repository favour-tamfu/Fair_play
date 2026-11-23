"""Match meter batches against songs WITHOUT the server (no Docker needed). Uses only fairplay_core.

    # 1. catalogue self-test: cut the song itself into 10 s windows and match them (should be ~100 %)
    python -m server.tools.match_offline --song data\\song.wav --selftest

    # 2. real test: batches recorded by Laptop A's meter while the song played on a speaker
    python -m server.tools.match_offline --song data\\song.wav  device_state\\M-07.db
    python -m server.tools.match_offline --song data\\song.wav  data\\batches\\   (folder of *.json)

Batch sources: A's outbox SQLite (.db: tables outbox + dead), a folder of .json files, single .json files, or
.jsonl (one batch per line). Signatures are checked with contract/meters/<meter_id>.pub.json when it exists.
Several --song options build a small catalogue (more realistic: the matcher must pick the right one).
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

import numpy as np

from fairplay_core.constants import FRAME_S, WINDOW_SAMPLES
from fairplay_core.landmarks import MemoryIndex, make_hashes, match_window
from fairplay_core.peaks import extract_peaks, resample_to_8k
from fairplay_core.schema import Batch
from fairplay_core.signing import load_pub, verify_batch
from server.tools.golden_sha import load_wav_float32

METERS_DIR = Path(__file__).resolve().parents[2] / "contract" / "meters"


def load_song_8k(path: Path) -> np.ndarray:
    x, sr = load_wav_float32(path)
    if sr == 48000:
        return resample_to_8k(x)
    if sr != 8000:
        raise SystemExit(f"{path}: {sr} Hz not supported (need 8000 or 48000 Hz WAV)")
    return x


def read_batches(sources: list[str]) -> list[dict]:
    out: list[dict] = []
    for src in sources:
        p = Path(src)
        if p.is_dir():
            files = sorted(p.glob("*.json"))
        else:
            files = [p]
        for f in files:
            if f.suffix == ".db":
                con = sqlite3.connect(f)
                for table in ("outbox", "dead"):
                    try:
                        out += [json.loads(r[0]) for r in con.execute(f"SELECT json FROM {table} ORDER BY seq")]
                    except sqlite3.OperationalError:
                        pass
                con.close()
            elif f.suffix == ".jsonl":
                out += [json.loads(line) for line in f.read_text(encoding="utf-8").splitlines() if line.strip()]
            else:
                doc = json.loads(f.read_text(encoding="utf-8"))
                out += doc if isinstance(doc, list) else [doc]
    out.sort(key=lambda b: (b.get("meter_id", ""), b.get("window_start", ""), b.get("seq", 0)))
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--song", action="append", required=True, help="WAV file (8 or 48 kHz); repeat for more songs")
    ap.add_argument("--selftest", action="store_true", help="match the song's own 10 s windows")
    ap.add_argument("batches", nargs="*", help="outbox .db, folder of .json, .json or .jsonl files")
    a = ap.parse_args(argv)

    # ---- catalogue: index every song (song_id = file name)
    idx, songs = MemoryIndex(), {}
    for s in a.song:
        path = Path(s)
        x8 = load_song_8k(path)
        t0 = time.perf_counter()
        n = idx.add_peaks(path.stem, extract_peaks(x8))
        songs[path.stem] = x8
        print(f"indexed {path.name}: {len(x8) / 8000:.1f} s, {n} hashes ({(time.perf_counter() - t0) * 1000:.0f} ms)")

    if a.selftest:
        print("\nself-test: the song's own 10 s windows, every 5 s")
        for sid, x8 in songs.items():
            hits = total = 0
            for start in range(0, len(x8) - WINDOW_SAMPLES + 1, 5 * 8000):
                r = match_window(make_hashes(extract_peaks(x8[start:start + WINDOW_SAMPLES])), idx)
                ok = r.accepted and r.song_id == sid and abs(r.offset_s - start / 8000) <= FRAME_S * 1.5
                hits += ok
                total += 1
                print(f"  {sid} @ {start / 8000:5.1f}s -> {r.song_id} @ {r.offset_s:5.1f}s score {r.best_score:4d} "
                      f"(2nd {r.second_score:3d}) {'OK' if ok else 'MISS'}")
            print(f"  {sid}: {hits}/{total} windows correct")

    batches = read_batches(a.batches) if a.batches else []
    if not batches:
        return 0

    print(f"\n{len(batches)} batches")
    print(f"{'meter':6} {'seq':>5} {'window_start (UTC)':24} {'peaks':>5} {'dB':>6} {'sig':4} "
          f"{'song':28} {'offset':>7} {'score':>5} {'2nd':>4} {'conf':>5} result")
    pubs: dict[str, dict | None] = {}
    accepted = 0
    prev = None
    for b in batches:
        mid = b.get("meter_id", "?")
        if mid not in pubs:
            f = METERS_DIR / f"{mid}.pub.json"
            pubs[mid] = load_pub(f) if f.exists() else None
        sig = "?" if pubs[mid] is None else ("ok" if verify_batch(pubs[mid]["public_key_b64"], b) else "BAD")
        try:
            batch = Batch.model_validate(b)
        except Exception as e:  # show, never crash on one bad batch
            print(f"{mid:6} {b.get('seq', '?'):>5} INVALID: {str(e).splitlines()[0]}")
            continue
        r = match_window(make_hashes(batch.peak_records()), idx)
        accepted += r.accepted
        note = ""
        if r.accepted and prev and prev[0] == r.song_id:
            # same play? song offset should advance like the clock (brief §6, tolerance 5 s)
            drift = (r.offset_s - prev[1]) - (batch.window_start_dt - prev[2]).total_seconds()
            note = f"  drift {drift:+.1f}s {'same play' if abs(drift) <= 5 else 'JUMP'}"
        if r.accepted:
            prev = (r.song_id, r.offset_s, batch.window_start_dt)
        print(f"{mid:6} {batch.seq:>5} {batch.window_start:24} {batch.n_peaks:>5} {batch.loudness_db:>6.1f} {sig:4} "
              f"{(r.song_id or '-')[:28]:28} {r.offset_s:>6.1f}s {r.best_score:>5} {r.second_score:>4} "
              f"{r.confidence:>5.2f} {'MATCH' if r.accepted else 'no match'}{note}")
    print(f"\naccepted {accepted}/{len(batches)} windows")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
