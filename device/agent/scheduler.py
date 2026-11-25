"""Window scheduler (A-T02): cuts a 48 kHz sample stream into 10 s analysis windows.

demo  = a 10 s window every 10 s (continuous)
field = a 10 s window every 60 s (the other 50 s are skipped)

Input is an iterable of (wall_time_of_first_sample, float32 block) pairs from
device.agent.capture. Blocks should be contiguous; a None item marks a gap.

Window times come from the sample count since the first block (exact spacing), but they are
re-anchored to the wall clock whenever a block's wall time differs from the counted time by more
than CLOCK_JUMP_S: after the laptop slept or the audio stream stalled, the stream resumes without
a gap marker, and without this check every later window would keep the lost time (R-020: M-07 was
3 h 54 min behind after a sleep). The re-anchor is handled like a gap (the partial window is dropped).

Each emitted Window carries what the batcher needs: 48 kHz samples, 8 kHz samples,
RMS loudness (from the 48 kHz window) and the peaks extracted from the 8 kHz window.
"""
from dataclasses import dataclass
from typing import Iterable, Iterator, Tuple

import numpy as np

from fairplay_core.constants import CAPTURE_RATE, WINDOW_S
from fairplay_core.peaks import extract_peaks, resample_to_8k, rms_dbfs

WINDOW_SAMPLES_48 = WINDOW_S * CAPTURE_RATE
PERIOD_S = {"demo": 10, "field": 60}
CLOCK_JUMP_S = 1.0   # counted time vs wall time difference that forces a re-anchor (R-020)


@dataclass
class Window:
    start_utc: float        # epoch seconds of the first sample of the window
    samples48: np.ndarray   # float32 mono, 48 kHz, WINDOW_S seconds
    x8: np.ndarray          # float32 mono, 8 kHz
    loudness_db: float      # RMS dBFS of samples48, 1 decimal, in -100..0
    peaks: np.ndarray       # structured peaks from fairplay_core.peaks.extract_peaks


class Scheduler:
    def __init__(self, mode: str = "demo"):
        if mode not in PERIOD_S:
            raise ValueError(f"mode must be one of {sorted(PERIOD_S)}, got {mode!r}")
        self.mode = mode
        self.period_s = PERIOD_S[mode]
        self.reanchors = 0   # times the window clock was re-set from the wall clock (sleep, stalled stream)

    def windows(self, blocks: Iterable[Tuple[float, np.ndarray]]) -> Iterator[Window]:
        """Yield one Window per period, as soon as enough audio has arrived.

        The first block's wall time anchors the window start times:
        window k starts at t0 + k * period_s.
        """
        period = self.period_s * CAPTURE_RATE
        t0 = None
        buf = np.empty(0, dtype=np.float32)
        buf_start = 0   # absolute sample index of buf[0]
        pos = 0         # absolute sample index just after the last appended sample
        next_start = 0  # absolute sample index where the next window starts

        for item in blocks:
            if item is None:  # gap: audio was lost before the next block; start over from it
                t0, buf, buf_start, pos, next_start = None, np.empty(0, dtype=np.float32), 0, 0, 0
                continue
            wall, block = item
            block = np.asarray(block, dtype=np.float32).reshape(-1)
            if t0 is not None and abs(float(wall) - (t0 + pos / CAPTURE_RATE)) > CLOCK_JUMP_S:
                # the counted time no longer matches the clock (sleep, stalled stream): start over from this block
                t0, buf, buf_start, pos, next_start = None, np.empty(0, dtype=np.float32), 0, 0, 0
                self.reanchors += 1
            if t0 is None:
                t0 = float(wall)
            buf = np.concatenate([buf, block])
            pos += block.size

            while next_start + WINDOW_SAMPLES_48 <= pos:
                off = next_start - buf_start
                samples = buf[off : off + WINDOW_SAMPLES_48].copy()
                x8 = resample_to_8k(samples)
                yield Window(
                    start_utc=t0 + next_start / CAPTURE_RATE,
                    samples48=samples,
                    x8=x8,
                    loudness_db=rms_dbfs(samples),
                    peaks=extract_peaks(x8),
                )
                next_start += period
                drop = next_start - buf_start
                if drop > 0:
                    buf = buf[drop:]
                    buf_start = next_start
