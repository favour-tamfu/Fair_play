"""Virtual meter (A-T07): the same agent pipeline, fed with audio files instead of the mic.

  python -m device.virtual --config device\\config\\M-11.toml --playlist data\\playlists\\akwa.txt
  python -m device.virtual --config device\\config\\M-11.toml --playlist akwa.txt --noise data\\recordings\\crowd.wav --snr-db 10
  python -m device.virtual --config device\\config\\M-12.toml --playlist akwa.txt --time simulated --start 2026-11-24T19:00:00Z --speed 20

--time realtime : plays at real speed (or --speed), timestamps are the real clock (+ --clock-offset-s).
--time simulated: processes as fast as possible, timestamps start at --start (replays a whole evening).
The playlist is a text file with one audio path per line (# comments and blank lines are skipped).
"""
import argparse
import os
import sys
import time
import tomllib
from datetime import datetime, timezone

import numpy as np

from device.agent.capture import FileSource
from device.agent.__main__ import run_pipeline
from fairplay_core.constants import CAPTURE_RATE

BLOCK = 4800  # 0.1 s at 48 kHz, same as the mic path


def read_playlist(path: str) -> list:
    base = os.path.dirname(os.path.abspath(path))
    items = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            items.append(s if os.path.isabs(s) else os.path.join(base, s))
    if not items:
        raise SystemExit(f"playlist {path} has no songs")
    return items


def mix_noise(audio: np.ndarray, noise: np.ndarray, snr_db: float) -> np.ndarray:
    """Add noise (looped to the audio length) at the given signal-to-noise ratio in dB."""
    if noise.size == 0:
        return audio
    reps = int(np.ceil(audio.size / noise.size))
    tiled = np.tile(noise, reps)[: audio.size]
    p_sig = float(np.mean(np.square(audio))) + 1e-12
    p_noise = float(np.mean(np.square(tiled))) + 1e-12
    gain = np.sqrt(p_sig / (p_noise * (10.0 ** (snr_db / 10.0))))
    return (audio + gain * tiled).astype(np.float32)


def make_blocks(audio: np.ndarray, start_utc: float, realtime: bool, speed: float = 1.0,
                blocksize: int = BLOCK, sleep=time.sleep):
    """Yield (wall time of first sample, block) pairs. Realtime sleeps between blocks."""
    for i in range(0, audio.size, blocksize):
        block = audio[i:i + blocksize]
        yield start_utc + i / CAPTURE_RATE, block
        if realtime:
            sleep(block.size / CAPTURE_RATE / max(speed, 1e-6))


def _parse(argv):
    p = argparse.ArgumentParser(prog="device.virtual", description="virtual meter (A-T07)")
    p.add_argument("--config", required=True)
    p.add_argument("--playlist", required=True)
    p.add_argument("--noise", default=None, help="crowd/room noise WAV to mix in")
    p.add_argument("--snr-db", type=float, default=10.0)
    p.add_argument("--time", choices=["realtime", "simulated"], default="realtime")
    p.add_argument("--start", default=None, help="simulated start, e.g. 2026-11-24T19:00:00Z")
    p.add_argument("--speed", type=float, default=1.0, help="realtime speed factor")
    p.add_argument("--clock-offset-s", type=float, default=0.0)
    p.add_argument("--mode", choices=["demo", "field"], default=None)
    return p.parse_args(argv)


def run(argv=None) -> int:
    args = _parse(argv)
    with open(args.config, "rb") as fh:
        cfg = tomllib.load(fh)
    mode = args.mode or cfg.get("mode", "demo")

    songs = [FileSource(path).load() for path in read_playlist(args.playlist)]
    audio = np.concatenate(songs).astype(np.float32)
    if args.noise:
        noise = FileSource(args.noise).load()
        audio = mix_noise(audio, noise, args.snr_db)

    realtime = args.time == "realtime"
    if realtime:
        start = time.time()
    else:
        if not args.start:
            raise SystemExit("--time simulated needs --start")
        start = datetime.strptime(args.start, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
    start += args.clock_offset_s

    blocks = make_blocks(audio, start, realtime=realtime, speed=args.speed)
    label = f"virtual {args.time} {len(songs)} songs" + (f" + noise {args.snr_db} dB" if args.noise else "")
    made = run_pipeline(cfg, mode, blocks, label, show_screen=realtime)
    print(f"windows made: {made}")
    return 0


if __name__ == "__main__":
    sys.exit(run())
