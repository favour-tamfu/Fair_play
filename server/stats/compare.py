"""Flat split vs Fair Play, measured against the mock month's ground truth (brief §7.4) — B-T11.

    compare_flat(conn, pot_fcfa) -> compare_flat.schema.json body

Per artist of the mock catalogue (the flat advance is paid per artist):
  S_true[a]  = artist's share of the TRUE plays (mock_truth: what really played, every play counts 1)
  flat       = 1 / n_artists for everyone
  Fair Play  = artist's share in the latest standardised mock_month stats run (sum of its songs' shares)
  misallocated = 0.5 × pot × Σ_a |S[a] − S_true[a]|   (FCFA that would go to the wrong artists)
n_artists = 0 means: not computed (no mock month imported, or no stats run yet).
"""
from __future__ import annotations

from typing import Any

import pandas as pd


def misallocated(pot_fcfa: int, est: pd.Series, true: pd.Series) -> int:
    idx = true.index.union(est.index)
    diff = (est.reindex(idx, fill_value=0.0) - true.reindex(idx, fill_value=0.0)).abs().sum()
    return int(round(0.5 * pot_fcfa * diff))


def compare_flat(conn, pot_fcfa: int) -> dict[str, Any]:
    empty = {"pot_fcfa": pot_fcfa, "n_artists": 0, "flat_each_fcfa": 0, "misallocated_flat_fcfa": 0,
             "misallocated_fairplay_fcfa": 0, "basis": "mock_month_truth"}
    run = conn.execute("""SELECT stats_run_id FROM stats_runs WHERE period = 'mock_month' AND mode = 'standardised'
                           AND finished_at IS NOT NULL ORDER BY finished_at DESC LIMIT 1""").fetchone()
    rid = run["stats_run_id"] if run else None
    artists = [r["artist_name"] for r in conn.execute(
        "SELECT DISTINCT artist_name FROM songs WHERE source = 'mock' AND artist_name IS NOT NULL ORDER BY 1")]
    true = pd.DataFrame(conn.execute("""SELECT s.artist_name, count(*) AS n FROM mock_truth t
                                        JOIN songs s USING (song_id) GROUP BY 1""").fetchall(),
                        columns=["artist_name", "n"])
    if rid is None or not artists or true.empty:
        return empty
    s_true = true.set_index("artist_name")["n"].astype(float)
    s_true /= s_true.sum()
    est = pd.DataFrame(conn.execute("""SELECT s.artist_name, sum(sh.share) AS share FROM shares sh
                                       JOIN songs s USING (song_id) WHERE sh.stats_run_id = %s GROUP BY 1""",
                                    (rid,)).fetchall(), columns=["artist_name", "share"])
    s_est = est.set_index("artist_name")["share"].astype(float)
    if s_est.sum() > 0:
        s_est /= s_est.sum()                    # mock run covers mock songs only; renormalise defensively
    n = len(artists)
    flat = pd.Series(1.0 / n, index=artists)
    return {"pot_fcfa": pot_fcfa, "n_artists": n, "flat_each_fcfa": pot_fcfa // n,
            "misallocated_flat_fcfa": misallocated(pot_fcfa, flat, s_true),
            "misallocated_fairplay_fcfa": misallocated(pot_fcfa, s_est, s_true), "basis": "mock_month_truth"}
