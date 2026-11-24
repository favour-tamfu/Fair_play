"""Fair-play weights, rule version sr-1.0 (brief §7). Pure functions: data frames in, data frames out, no DB.

    result = compute_weights(plays, songs, windows)
    result.weights  -> DataFrame[play_id, weight, reasons]   (one row per input play, same order as the input)
    result.flags    -> list of {type, song_id, venue_id, meter_id, detail}  (rows for the `flags` table)

Inputs (extra columns are ignored):
    plays    play_id, venue_id, song_id, started_at (UTC); optional meter_id, loudness_db
    songs    song_id, duration_s                      (optional; unknown length -> config.DEFAULT_SONG_LENGTH_S)
    windows  meter_id, loudness_db; optional received (optional; used only for the audience loudness test)

Order of rules (brief §7.2 "applied after 7.1, multiplicatively"):
    1. repeat streak + cooldown (§7.1 reference algorithm, exactly)  -> streak_1..4 | cooldown
    2. loop flag (no weight change; 7.1 already limits it)            -> + loop
    3. audience check                                                 -> + low_audience
    4. concentration check per song                                   -> + concentration
D-009: steps 3-4 only flag for SONACAM review; they change the weight (x0.5 / cap) only when
config.MODIFIERS_ADJUST_WEIGHTS is True (brief §7.2 original). Streak/cooldown is the only automatic weight.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from server import config
from server.stats import modifiers

SUPPORTED_RULES = ("sr-1.0",)


@dataclass
class FairPlayResult:
    weights: pd.DataFrame
    flags: list[dict] = field(default_factory=list)


def to_ns(s: pd.Series) -> np.ndarray:
    """Any datetime-like series (tz-aware, naive=UTC, ISO strings) -> int64 nanoseconds since epoch."""
    return pd.to_datetime(s, utc=True).dt.as_unit("ns").astype("int64").to_numpy()


def event_order(plays: pd.DataFrame) -> np.ndarray:
    """Row positions sorted by venue, then event time, then play_id (deterministic for equal start times)."""
    return np.lexsort((plays["play_id"].to_numpy(), to_ns(plays["started_at"]), plays["venue_id"].to_numpy()))


def streak_weights(venue: np.ndarray, song: np.ndarray, t_ns: np.ndarray,
                   weights=config.STREAK_WEIGHTS) -> tuple[np.ndarray, list[str]]:
    """§7.1 reference algorithm. Inputs must already be in event order (venue, started_at).

    The reference increments `others_since` of every other song in the venue on each play — O(plays × songs).
    Equivalent O(plays): `others_since` of song s at play i = (plays in the venue strictly between s's mark and i)
    − (s's own cooldown plays since the mark), where the mark is s's last play that reset others_since
    (its first play, or any play that was not a cooldown play).
    """
    n = len(song)
    w = np.zeros(n)
    why: list[str] = [""] * n
    cool_ns = int(config.COOLDOWN_H * 3600e9)
    reset_ns = int(config.RESET_MIN * 60e9)
    state: dict = {}
    pos = -1
    prev_venue = object()
    for i in range(n):
        if venue[i] != prev_venue:
            state, pos, prev_venue = {}, -1, venue[i]
        pos += 1
        st = state.get(song[i])
        if st is None:                                     # [streak, last_play, cooldown_until, mark, own_since]
            st = state[song[i]] = [0, None, None, pos, 0]
        others = pos - st[3] - 1 - st[4]
        t = t_ns[i]
        if st[2] is not None:
            if t >= st[2] and others >= config.COOLDOWN_OTHER_SONGS:
                st[2], st[0] = None, 0
            else:
                w[i], why[i] = 0.0, "cooldown"
                st[1] = t
                st[4] += 1                                 # own play: does not count as "other", mark unchanged
                continue
        if st[0] > 0 and others >= config.RESET_OTHER_SONGS and t - st[1] >= reset_ns:
            st[0] = 0
        st[0] += 1
        w[i], why[i] = weights[st[0] - 1], f"streak_{st[0]}"
        if st[0] == len(weights):
            st[2] = t + cool_ns
        st[1], st[3], st[4] = t, pos, 0                    # others_since = 0
    return w, why


def compute_weights(plays: pd.DataFrame, songs: Optional[pd.DataFrame] = None,
                    windows: Optional[pd.DataFrame] = None, rule_version: str = config.RULE_VERSION) -> FairPlayResult:
    if rule_version not in SUPPORTED_RULES:
        raise ValueError(f"unknown rule_version {rule_version!r} (supported: {SUPPORTED_RULES})")
    if plays.empty:
        return FairPlayResult(pd.DataFrame({"play_id": [], "weight": [], "reasons": []}))

    order = event_order(plays)
    p = plays.iloc[order].reset_index(drop=True)
    t_ns = to_ns(p["started_at"])
    venue, song = p["venue_id"].to_numpy(), p["song_id"].to_numpy()

    w, first = streak_weights(venue, song, t_ns)
    reasons = [[r] for r in first]
    flags = modifiers.cooldown_flags(p, w, first)

    length = modifiers.song_lengths(p, songs)
    looped, loop_flags = modifiers.loop_flags(venue, song, t_ns, length)
    for i in np.flatnonzero(looped):
        reasons[i].append("loop")
    flags += loop_flags

    low, aud_flags = modifiers.low_audience(p, t_ns, windows)
    for i in np.flatnonzero(low):
        reasons[i].append("low_audience")
    if config.MODIFIERS_ADJUST_WEIGHTS:
        w = np.where(low, w * config.AUDIENCE_FACTOR, w)
    flags += aud_flags

    w, over, conc_flags = modifiers.concentration_cap(p, w, apply=config.MODIFIERS_ADJUST_WEIGHTS)
    for i in np.flatnonzero(over):
        reasons[i].append("concentration")
    flags += conc_flags

    out = pd.DataFrame({"play_id": p["play_id"].to_numpy(), "weight": w, "reasons": reasons})
    back = np.empty_like(order)
    back[order] = np.arange(len(order))
    return FairPlayResult(out.iloc[back].reset_index(drop=True), flags)
