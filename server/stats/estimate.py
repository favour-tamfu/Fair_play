"""National share estimates from sampled meters (brief §7.3). Pure functions, no DB.

    est = estimate_shares(play_w, meters, rng_seed=...)

play_w   one row per play: meter_id, song_id, weight              (weight = sr-1.0 weight, or 1 in raw mode)
meters   one row per meter that has plays: meter_id, stratum, bars_in_stratum, catch_rate, received_s, open_s

Per meter:  L = received_s / open_s (listening fraction, clipped to (0, 1]; unknown -> 1)
            c = catch_rate (default 0.8 until calibrated)
            E[song] = weighted plays / (c × L)                      (expanded: what the meter would have heard)
Strata:     each meter represents bars_in_stratum / n_meters_in_stratum bars (unknown stratum -> the meter's venue
            alone, 1 bar).
National:   T[song] = Σ_meters E × bars_represented;  S = T / Σ T.
Range:      bootstrap — resample meters with replacement within each stratum, n_boot times (seeded), 5th–95th
            percentile of S. The range is widened to include the point estimate if needed.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from server import config


@dataclass
class Estimate:
    shares: pd.DataFrame           # song_id, raw_plays, weighted_plays, expanded, share, ci_low, ci_high (share desc)
    meters: pd.DataFrame           # meter_id, stratum, L, c, bars_represented


def open_seconds(start: datetime, end: datetime, open_hour: int, close_hour: int, extra_hours=()) -> float:
    """Seconds of [start, end) that fall in the venue's open hours (local, e.g. 18 -> 2 = 18:00-02:00) or in any
    extra local hour-of-day (the meter's own activity profile, brief §7.3.1). Hour resolution."""
    if end <= start:
        return 0.0
    if open_hour == close_hour:
        hours = set(range(24))
    elif open_hour < close_hour:
        hours = set(range(open_hour, close_hour))
    else:
        hours = set(range(open_hour, 24)) | set(range(0, close_hour))
    hours |= {int(h) % 24 for h in extra_hours}
    off = timedelta(hours=config.LOCAL_UTC_OFFSET_H)
    t = start.replace(minute=0, second=0, microsecond=0)
    total = 0.0
    while t < end:
        nxt = t + timedelta(hours=1)
        if (t + off).hour in hours:
            total += (min(nxt, end) - max(t, start)).total_seconds()
        t = nxt
    return total


def listening_fraction(received_s, open_s) -> np.ndarray:
    r = np.asarray(received_s, dtype=float)
    o = np.asarray(open_s, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        L = np.where((o > 0) & (r > 0), r / o, 1.0)
    return np.clip(L, 1e-6, 1.0)


def estimate_shares(play_w: pd.DataFrame, meters: pd.DataFrame, n_boot: int = config.BOOTSTRAP_N,
                    rng_seed: int = config.BOOTSTRAP_SEED) -> Estimate:
    cols = ["song_id", "raw_plays", "weighted_plays", "expanded", "share", "ci_low", "ci_high"]
    if play_w.empty:
        return Estimate(pd.DataFrame(columns=cols), pd.DataFrame())

    m = meters.drop_duplicates("meter_id").set_index("meter_id")
    m = m.reindex(sorted(set(play_w["meter_id"])))
    stratum = m["stratum"].where(m["stratum"].notna(), "venue:" + m.get("venue_id", m.index.to_series()).astype(str))
    stratum = stratum.where(stratum.notna(), "meter:" + m.index.to_series())
    n_in = stratum.map(stratum.value_counts())
    N = pd.to_numeric(m["bars_in_stratum"], errors="coerce").where(lambda s: s > 0)
    bars_rep = (N / n_in).fillna(1.0).to_numpy(dtype=float)
    c = pd.to_numeric(m["catch_rate"], errors="coerce").where(lambda s: s > 0).fillna(config.DEFAULT_CATCH_RATE)
    c = c.clip(upper=1.0).to_numpy(dtype=float)
    L = listening_fraction(m["received_s"], m["open_s"])

    songs = sorted(set(play_w["song_id"]))
    mi = pd.Index(m.index).get_indexer(play_w["meter_id"])
    si = pd.Index(songs).get_indexer(play_w["song_id"])
    W = np.zeros((len(m), len(songs)))                         # weighted plays per meter × song
    np.add.at(W, (mi, si), play_w["weight"].to_numpy(dtype=float))
    raw = np.bincount(si, minlength=len(songs))
    X = W / (c * L)[:, None] * bars_rep[:, None]               # expanded national contribution per meter × song

    T = X.sum(axis=0)
    total = T.sum()
    share = T / total if total > 0 else np.zeros(len(songs))

    # bootstrap: resample meters within strata (counts per meter ~ multinomial(n_stratum, uniform))
    rng = np.random.default_rng(rng_seed)
    K = np.zeros((n_boot, len(m)))
    for s in pd.unique(stratum):
        idx = np.flatnonzero((stratum == s).to_numpy())
        K[:, idx] = rng.multinomial(len(idx), np.full(len(idx), 1 / len(idx)), size=n_boot)
    TB = K @ X
    tot_b = TB.sum(axis=1, keepdims=True)
    SB = np.divide(TB, tot_b, out=np.zeros_like(TB), where=tot_b > 0)
    lo, hi = np.percentile(SB, [config.CI_PCTL_LOW, config.CI_PCTL_HIGH], axis=0)
    lo, hi = np.minimum(lo, share), np.maximum(hi, share)

    out = pd.DataFrame({"song_id": songs, "raw_plays": raw, "weighted_plays": W.sum(axis=0), "expanded": T,
                        "share": share, "ci_low": lo, "ci_high": hi})
    out = out.sort_values(["share", "song_id"], ascending=[False, True], kind="stable").reset_index(drop=True)
    meters_out = pd.DataFrame({"meter_id": m.index, "stratum": stratum.to_numpy(), "L": L, "c": c,
                               "bars_represented": bars_rep})
    return Estimate(out, meters_out)


def escrow_share(unidentified_s: float, identified_s: float) -> float:
    """Unidentified music time as a share of all music time (brief §7.3.7) — reported separately, not redistributed."""
    total = unidentified_s + identified_s
    return float(unidentified_s / total) if total > 0 else 0.0
