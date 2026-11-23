"""Audio sources for the device agent (A-T02).

MicSource  - laptop microphone via sounddevice (WASAPI when available), 48 kHz mono.
FileSource - WAV/FLAC/OGG via soundfile, MP3 via ffmpeg; used by virtual meters and tests.

Both yield (wall_time_of_first_sample, float32 mono 48 kHz block) pairs, which
device.agent.scheduler.Scheduler turns into 10 s windows.

CLI:
    python -m device.agent.capture --seconds 25 --mode demo
    python -m device.agent.capture --seconds 25 --input file:data\\songs\\x.wav --save-debug-wav
"""
import argparse
import math
import os
import queue
import shutil
import subprocess
import threading
import time
from datetime import datetime, timezone
from fractions import Fraction
from typing import Iterator, Optional, Tuple

import numpy as np

from fairplay_core.constants import CAPTURE_RATE
from device.agent.scheduler import Scheduler, Window

Block = Tuple[float, np.ndarray]


class MicSource:
    """Laptop microphone, 48 kHz mono, float32."""

    def __init__(self, device: Optional[int] = None, samplerate: int = CAPTURE_RATE, blocksize: int = 4800):
        self.device = device if device is not None else self._pick_wasapi_input()
        self.samplerate = samplerate
        self.blocksize = blocksize
        self.overflows = 0

    @staticmethod
    def _pick_wasapi_input() -> Optional[int]:
        import sounddevice as sd

        for api in sd.query_hostapis():
            if "WASAPI" in api["name"]:
                idx = api.get("default_input_device", -1)
                if idx is not None and idx >= 0:
                    return idx
        return None

    def blocks(self, duration_s: Optional[float] = None) -> Iterator[Block]:
        import sounddevice as sd

        q: "queue.Queue[Block]" = queue.Queue(maxsize=600)  # about 60 s of 0.1 s blocks
        state = {"offset": None}

        def callback(indata, frames, time_info, status):
            if status:
                self.overflows += 1
            wall = state["offset"] + time_info.inputBufferAdcTime
            try:
                q.put_nowait((wall, indata[:, 0].copy()))
            except queue.Full:
                self.overflows += 1

        def open_stream(device):
            return sd.InputStream(
                device=device,
                channels=1,
                samplerate=self.samplerate,
                blocksize=self.blocksize,
                dtype="float32",
                callback=callback,
            )

        try:
            stream = open_stream(self.device)
        except sd.PortAudioError:
            stream = open_stream(None)  # fall back to the default input device

        with stream:
            # Map PortAudio stream time to wall-clock time once, at start.
            state["offset"] = time.time() - stream.time
            started = time.monotonic()
            while True:
                if duration_s is not None and time.monotonic() - started >= duration_s:
                    break
                try:
                    yield q.get(timeout=1.0)
                except queue.Empty:
                    continue


class FileSource:
    """Decode an audio file to 48 kHz mono and yield it as blocks.

    realtime=True sleeps between blocks (virtual meter in real time);
    realtime=False yields as fast as possible (replay and tests).
    """

    def __init__(
        self,
        path: str,
        realtime: bool = False,
        start_utc: Optional[float] = None,
        blocksize: int = 4800,
        duration_s: Optional[float] = None,
    ):
        self.path = path
        self.realtime = realtime
        self.start_utc = start_utc
        self.blocksize = blocksize
        self.duration_s = duration_s

    def load(self) -> np.ndarray:
        ext = os.path.splitext(self.path)[1].lower()
        if ext == ".mp3":
            x = self._load_mp3()
        else:
            import soundfile as sf

            data, sr = sf.read(self.path, dtype="float32", always_2d=True)
            x = data.mean(axis=1).astype(np.float32)
            if sr != CAPTURE_RATE:
                x = _resample(x, sr, CAPTURE_RATE)
        if self.duration_s is not None:
            x = x[: int(self.duration_s * CAPTURE_RATE)]
        return x.astype(np.float32)

    def _load_mp3(self) -> np.ndarray:
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg is None:
            raise RuntimeError("MP3 input needs ffmpeg on PATH (winget install Gyan.FFmpeg)")
        out = subprocess.run(
            [ffmpeg, "-v", "error", "-i", self.path, "-f", "f32le", "-ac", "1", "-ar", str(CAPTURE_RATE), "-"],
            capture_output=True,
            check=True,
        ).stdout
        return np.frombuffer(out, dtype=np.float32).copy()

    def blocks(self) -> Iterator[Block]:
        x = self.load()
        t0 = self.start_utc if self.start_utc is not None else time.time()
        for i in range(0, x.size, self.blocksize):
            block = x[i : i + self.blocksize]
            yield t0 + i / CAPTURE_RATE, block
            if self.realtime:
                time.sleep(block.size / CAPTURE_RATE)


def _resample(x: np.ndarray, sr_in: int, sr_out: int) -> np.ndarray:
    from scipy.signal import resample_poly

    frac = Fraction(sr_out, sr_in)
    return resample_poly(x, frac.numerator, frac.denominator).astype(np.float32)


def _save_debug(win: Window, folder: str) -> str:
    import soundfile as sf

    os.makedirs(folder, exist_ok=True)
    stamp = datetime.fromtimestamp(win.start_utc, tz=timezone.utc).strftime("%Y%m%dT%H%M%S")
    path = os.path.join(folder, f"window_{stamp}.wav")
    sf.write(path, win.samples48, CAPTURE_RATE, subtype="FLOAT")
    return path


def _parse_args(argv=None):
    p = argparse.ArgumentParser(description="SoundProof capture check (A-T02)")
    p.add_argument("--seconds", type=float, default=25.0, help="how long to capture")
    p.add_argument("--mode", choices=["demo", "field"], default="demo")
    p.add_argument("--input", default="mic", help="'mic' or 'file:<path>'")
    p.add_argument("--device", type=int, default=None, help="sounddevice input index (mic only)")
    p.add_argument("--save-debug-wav", action="store_true", help="write each window to data/debug/")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)
    if args.input == "mic":
        source = MicSource(device=args.device)
        blocks = source.blocks(duration_s=args.seconds)
    elif args.input.startswith("file:"):
        source = FileSource(args.input[len("file:") :], realtime=False, duration_s=args.seconds)
        blocks = source.blocks()
    else:
        raise SystemExit("--input must be 'mic' or 'file:<path>'")

    count = 0
    for win in Scheduler(args.mode).windows(blocks):
        count += 1
        stamp = datetime.fromtimestamp(win.start_utc, tz=timezone.utc).isoformat(timespec="seconds")
        print(f"window {count}: start {stamp}  peaks {win.peaks.size}  loudness {win.loudness_db} dBFS")
        if args.save_debug_wav:
            print(f"  saved {_save_debug(win, os.path.join('data', 'debug'))}")
    if count == 0:
        print("no complete window captured (capture longer or use --mode demo)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
