"""sr-1.0 modifiers applied after the streak/cooldown weights (brief §7.2). Pure functions, no DB.

All functions take the plays frame already in event order (venue, started_at, play_id) — see fairplay.event_order.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from server import config


def _flag(type_: str, song_id, venue_id, detail: str, meter_id=None) -> dict:
    return {"type": type_, "song_id": song_id, "venue_id": venue_id, "meter_id": meter_id, "detail": detail}


def song_lengths(p: pd.DataFrame, songs: Optional[pd.DataFrame]) -> np.ndarray:
    """Song length in seconds for each play (unknown/zero -> config.DEFAULT_SONG_LENGTH_S)."""
    known = {}
    if songs is not None and not songs.empty and "duration_s" in songs:
        known = {s: float(d) for s, d in zip(songs["song_id"], songs["duration_s"]) if pd.notna(d) and d > 0}
    return np.array([known.get(s, config.DEFAULT_SONG_LENGTH_S) for s in p["song_id"]])


# ---------------------------------------------------------------- cooldown (summary flags only)

def cooldown_flags(p: pd.DataFrame, w: np.ndarray, why: list[str]) -> list[dict]:
    """One `cooldown` flag per (venue, song) that had zero-weight plays: '7 plays -> 3.75 counted, 2 in cooldown'."""
    df = pd.DataFrame({"venue_id": p["venue_id"], "song_id": p["song_id"], "w": w,
                       "cool": [r == "cooldown" for r in why]})
    g = df.groupby(["venue_id", "song_id"], sort=True).agg(raw=("w", "size"), counted=("w", "sum"), cool=("cool", "sum"))
    return [_flag("cooldown", s, v, f"{int(r.raw)} plays -> {r.counted:g} counted, {int(r.cool)} in cooldown")
            for (v, s), r in g[g["cool"] > 0].iterrows()]


# ---------------------------------------------------------------- loop

def loop_flags(venue: np.ndarray, song: np.ndarray, t_ns: np.ndarray, length_s: np.ndarray):
    """>= LOOP_MIN_RUN back-to-back plays of one song in a venue (no other song between), each starting
    song_length +- LOOP_GAP_TOL_S after the previous one -> every play of the run gets `loop`; one flag per run."""
    n = len(song)
    looped = np.zeros(n, dtype=bool)
    flags: list[dict] = []
    start = 0
    for i in range(1, n + 1):
        chained = (i < n and venue[i] == venue[i - 1] and song[i] == song[i - 1]
                   and abs((t_ns[i] - t_ns[i - 1]) / 1e9 - length_s[i]) <= config.LOOP_GAP_TOL_S)
        if chained:
            continue
        run = i - start
        if run >= config.LOOP_MIN_RUN:
            looped[start:i] = True
            off = config.LOCAL_UTC_OFFSET_H * 3_600_000_000_000                # flag text for people: local time
            t0 = pd.Timestamp(t_ns[start] + off).strftime("%Y-%m-%d %H:%M")
            t1 = pd.Timestamp(t_ns[i - 1] + off).strftime("%H:%M")
            flags.append(_flag("loop", song[start], venue[start],
                               f"{run} back-to-back plays {t0}-{t1} (Cameroon time), one song length apart"))
        start = i
    return looped, flags


# ---------------------------------------------------------------- audience factor

def low_audience(p: pd.DataFrame, t_ns: np.ndarray, windows: Optional[pd.DataFrame],
                 thresholds: Optional[pd.DataFrame] = None):
    """x0.5 if the play is quieter than its venue's AUDIENCE_PCTL-th percentile of window loudness over the period,
    or starts in a local hour holding < ACTIVE_HOUR_MIN_SHARE of the venue's plays.
    D-008 guards: loudness test only with >= AUDIENCE_MIN_WINDOWS venue windows and a known play loudness;
    active-hours test only with >= AUDIENCE_MIN_PLAYS venue plays (too few plays make every hour look 'inactive')."""
    n = len(p)
    venue = p["venue_id"].to_numpy()
    quiet = np.zeros(n, dtype=bool)
    off = np.zeros(n, dtype=bool)

    # loudness: venue threshold from that venue's meters' received windows
    # (or precomputed in SQL: thresholds = DataFrame[venue_id, n_windows, threshold_db])
    thr = None
    if thresholds is not None and not thresholds.empty:
        t = thresholds[thresholds["n_windows"] >= config.AUDIENCE_MIN_WINDOWS]
        thr = pd.Series(t["threshold_db"].to_numpy(dtype=float), index=t["venue_id"])
    elif windows is not None and not windows.empty and "loudness_db" in p:
        wv = windows
        if "received" in wv:
            wv = wv[wv["received"].fillna(True).astype(bool)]
        if "venue_id" not in wv:
            meter_venue = (p[["meter_id", "venue_id"]].drop_duplicates("meter_id").set_index("meter_id")["venue_id"]
                           if "meter_id" in p else pd.Series(dtype=object))
            wv = wv.assign(venue_id=wv["meter_id"].map(meter_venue))
        wv = wv.dropna(subset=["venue_id", "loudness_db"])
        counts = wv.groupby("venue_id")["loudness_db"].size()
        thr = wv.groupby("venue_id")["loudness_db"].quantile(config.AUDIENCE_PCTL / 100)
        thr = thr[counts >= config.AUDIENCE_MIN_WINDOWS]
    if thr is not None and "loudness_db" in p:
        play_thr = pd.Series(venue).map(thr).to_numpy(dtype=float)
        loud = pd.to_numeric(p["loudness_db"], errors="coerce").to_numpy(dtype=float)
        with np.errstate(invalid="ignore"):
            quiet = np.nan_to_num(loud, nan=np.inf) < np.nan_to_num(play_thr, nan=-np.inf)

    # active hours: local hour share of the venue's plays
    hour = ((t_ns // 3_600_000_000_000) + config.LOCAL_UTC_OFFSET_H) % 24
    df = pd.DataFrame({"venue_id": venue, "hour": hour})
    n_venue = df.groupby("venue_id")["hour"].transform("size").to_numpy()
    n_hour = df.groupby(["venue_id", "hour"])["hour"].transform("size").to_numpy()
    off = (n_venue >= config.AUDIENCE_MIN_PLAYS) & (n_hour / n_venue < config.ACTIVE_HOUR_MIN_SHARE)

    low = quiet | off
    flags = []
    if low.any():
        g = pd.DataFrame({"venue_id": venue, "quiet": quiet, "off": off, "low": low}).groupby("venue_id", sort=True).sum()
        for v, r in g[g["low"] > 0].iterrows():
            effect = f"x{config.AUDIENCE_FACTOR:g}" if config.MODIFIERS_ADJUST_WEIGHTS else "for review"
            flags.append(_flag("low_audience", None, v, f"{int(r.low)} plays {effect} "
                                                     f"(quiet room: {int(r.quiet)}, outside active hours: {int(r.off)})"))
    return low, flags


# ---------------------------------------------------------------- concentration

def concentration_cap(p: pd.DataFrame, w: np.ndarray, apply: bool = False):
    """Per song over the period: heard in < CONC_MIN_VENUES venues and top-2 venues > CONC_TOP2_SHARE of its weighted
    plays -> flag `concentration`; the cap is max(CONC_CAP_MIN, CONC_CAP_MULT x median weighted plays per (song, venue)
    over all songs). Returns (weights, over, flags): `over` marks plays in venues above the cap. The weights are scaled
    down to the cap only when apply=True (D-009: default is flag only, SONACAM decides).
    D-008 guard: only when the period has >= CONC_MIN_VENUES venues (else every song would be 'concentrated')."""
    w = w.copy()
    capped = np.zeros(len(w), dtype=bool)
    flags: list[dict] = []
    df = pd.DataFrame({"song_id": p["song_id"].to_numpy(), "venue_id": p["venue_id"].to_numpy(), "w": w})
    if df["venue_id"].nunique() < config.CONC_MIN_VENUES:
        return w, capped, flags
    sv = df.groupby(["song_id", "venue_id"], sort=True)["w"].sum()
    cap = max(config.CONC_CAP_MIN, config.CONC_CAP_MULT * float(sv.median()))
    for s, per_venue in sv.groupby(level="song_id", sort=True):
        per_venue = per_venue.droplevel("song_id").sort_values(ascending=False, kind="stable")
        total = per_venue.sum()
        if len(per_venue) >= config.CONC_MIN_VENUES or total <= 0:
            continue
        top2 = per_venue.iloc[:2].sum() / total
        if top2 <= config.CONC_TOP2_SHARE:
            continue
        n_capped = 0
        for v, vw in per_venue.items():
            if vw > cap:
                idx = np.flatnonzero((df["song_id"] == s).to_numpy() & (df["venue_id"] == v).to_numpy() & (w > 0))
                if apply:
                    w[idx] *= cap / vw
                capped[idx] = True
                n_capped += 1
        effect = "capped" if apply else "above it (for review)"
        flags.append(_flag("concentration", s, per_venue.index[0],
                           f"{len(per_venue)} venues, top 2 hold {top2:.0%} of {total:g} weighted plays; "
                           f"cap {cap:g} per venue, {n_capped} venue(s) {effect}"))
    return w, capped, flags
