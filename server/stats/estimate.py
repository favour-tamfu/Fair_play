"""Song shares from the meters (brief §7.3 as amended by D-011). Pure functions, no DB.

    est = estimate_shares(play_w, meters)

play_w   one row per play: meter_id, song_id, weight              (weight = sr-1.0 weight, or 1 in raw mode)
meters   meter_id, catch_rate                                     (optional; missing -> config.DEFAULT_CATCH_RATE)

D-011 — every bar has its own meter (full coverage, no sampling):
  - no scaling up to unmetered bars (no strata, no bars_represented) and no sampling range: ci_low = ci_high = share;
  - no opening hours / listening fraction: the meter reports what it hears; nothing heard = nothing counted;
  - unidentified music is not recorded (no escrow).
Per meter only the catch rate c is corrected for (a meter that catches 80 % of songs: 4 heard plays ≈ 5 played):
    T[song] = Σ_meters weighted plays / c ;   S = T / Σ T
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from server import config

COLS = ["song_id", "raw_plays", "weighted_plays", "expanded", "share", "ci_low", "ci_high"]


@dataclass
class Estimate:
    shares: pd.DataFrame           # COLS, sorted by share desc then song_id


def catch_rates(meter_ids, meters: Optional[pd.DataFrame]) -> np.ndarray:
    known = {}
    if meters is not None and not meters.empty and "catch_rate" in meters:
        known = {m: float(c) for m, c in zip(meters["meter_id"], meters["catch_rate"]) if pd.notna(c) and c > 0}
    return np.array([min(1.0, known.get(m, config.DEFAULT_CATCH_RATE)) for m in meter_ids])


def estimate_shares(play_w: pd.DataFrame, meters: Optional[pd.DataFrame] = None) -> Estimate:
    if play_w.empty:
        return Estimate(pd.DataFrame(columns=COLS))
    c = catch_rates(play_w["meter_id"].to_numpy(), meters)
    w = play_w["weight"].to_numpy(dtype=float)
    df = pd.DataFrame({"song_id": play_w["song_id"].to_numpy(), "w": w, "e": w / c})
    g = df.groupby("song_id", sort=True).agg(raw_plays=("w", "size"), weighted_plays=("w", "sum"), expanded=("e", "sum"))
    total = g["expanded"].sum()
    g["share"] = g["expanded"] / total if total > 0 else 0.0
    g["ci_low"] = g["share"]
    g["ci_high"] = g["share"]
    out = g.reset_index().sort_values(["share", "song_id"], ascending=[False, True], kind="stable")
    return Estimate(out[COLS].reset_index(drop=True))
