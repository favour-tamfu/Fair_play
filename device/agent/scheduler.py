"""Window scheduler (A-T02): cuts a 48 kHz sample stream into 10 s analysis windows.

demo  = a 10 s window every 10 s (continuous)
field = a 10 s window every 60 s (the other 50 s are skipped)

Each emitted Window carries everything the batcher needs: the 48 kHz samples,
the 8 kHz samples, the RMS loudness and the extracted peaks.
"""
from dataclasses import dataclass
from typing import Iterable, Iterator, Tuple

import numpy as np

from fairplay_core.constants import CAPTURE_RATE, WINDOW_S
from fairplay_core.peaks import extract_peaks, resample_to_8k, rms_dbfs

WINDOW_SAMPLES_48 = WINDOW_S * CAPTURE_RATE
PERIOD_S = {"demo": 10, "field": 60}


@dataclass
class Window:
    start_utc: float        # epoch seconds of the first sample in the window
    samples48: np.ndarray   # float32 mono, 48 kHz, WINDOW_S seconds
    x8: np.ndarray          # float32 mono, 8 kHz
    loudness_db: float      # RMS dBFS (1 decimal)
    peaks: np.ndarray       # structured peaks from core.peaks.extract_peaks


class Scheduler:
    def __init__(self, mode: str = "demo"):
        if mode not in PERIOD_S:
            raise ValueError(f"mode must be one of {sorted(PERIOD_S)}, got {mode!r}")
        self.mode = mode
        self.period_s = PERIOD_S[mode]

    def windows(self, blocks: Iterable[Tuple[float, np.ndarray]]) -> Iterator[Window]:
        """Consume (wall_time_of_first_sample, float32 block) pairs and yield Windows.

        Blocks are assumed contiguous (no gaps); the first block's wall time anchors all windows.
        """
        period = self.period_s * CAPTURE_RATE
        t0 = None
        buf = np.empty(0, dtype=np.float32)
        buf_start = 0          # absolute sample index of buf[0]
        pos = 0                # absolute sample index just after the last appended sample
        next_start = 0         # absolute sample index where the next window starts

        for wall, block in blocks:
            block = np.asarray(block, dtype=np.float32).reshape(-1)
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
