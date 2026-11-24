"""What each artist truly earned, as a cumulative percentage (B-T12 as decided by Person B, D-015).

    artist_shares(conn, period, mode) -> artist_shares.schema.json body

An artist is paid for all of their songs together: the shares of every song credited to the artist (songs.artist_name,
the lead artist) are added up, from the latest stats run of the period/mode. No money is computed: the result ends at
the share each artist truly earned; how SONACAM then pays it out is outside this version.
If the play ledger is not intact the result is frozen: no rows are given out until it is fixed (brief §9).
"""
from __future__ import annotations

from typing import Any

from server.ledger import audit

RULES = [
    "Every play a meter confirms is counted by the fair-play rules sr-1.0: repeats of the same song in a short time count "
    "less (1, 1, 0.5, 0.25) and then not at all for a 2-hour cooldown; loops, quiet rooms and concentrated plays are "
    "flagged for SONACAM review.",
    "Each meter's counted plays are divided by its catch rate (a meter that catches 80 % of songs: 4 heard ≈ 5 played).",
    "A song's share = its counted plays ÷ the counted plays of all songs in the period.",
    "An artist's share = the sum of the shares of all the artist's songs (artists are paid per artist, not per song).",
    "In this prototype each artist is registered as the 100 % owner of their own songs (mock ownership).",
]


def artist_shares(conn, period: str, mode: str = "standardised") -> dict[str, Any]:
    run = conn.execute("""SELECT stats_run_id, rule_version FROM stats_runs WHERE period = %s AND mode = %s
                          AND finished_at IS NOT NULL ORDER BY finished_at DESC LIMIT 1""", (period, mode)).fetchone()
    frozen = not audit.status(conn)["intact"]
    out = {"period": period, "mode": mode, "stats_run_id": run["stats_run_id"] if run else None,
           "rule_version": run["rule_version"] if run else None, "frozen": frozen, "rules": RULES, "rows": []}
    if run is None or frozen:
        return out
    rows = conn.execute("""SELECT COALESCE(s.artist_name, '') AS artist_name, sh.song_id, COALESCE(s.title, sh.song_id) AS title,
                                  sh.raw_plays, sh.weighted_plays, sh.share
                           FROM shares sh LEFT JOIN songs s USING (song_id) WHERE sh.stats_run_id = %s
                           ORDER BY sh.share DESC, sh.song_id""", (run["stats_run_id"],)).fetchall()
    by: dict[str, dict] = {}
    for r in rows:
        a = by.setdefault(r["artist_name"], {"artist_name": r["artist_name"], "share": 0.0, "raw_plays": 0,
                                             "counted_plays": 0.0, "songs": []})
        a["share"] += float(r["share"])
        a["raw_plays"] += int(r["raw_plays"] or 0)
        a["counted_plays"] += float(r["weighted_plays"] or 0)
        a["songs"].append({"song_id": r["song_id"], "title": r["title"], "share": float(r["share"]),
                           "raw_plays": int(r["raw_plays"] or 0), "counted_plays": round(float(r["weighted_plays"] or 0), 2)})
    ranked = sorted(by.values(), key=lambda a: (-a["share"], a["artist_name"]))
    for i, a in enumerate(ranked, 1):
        a["rank"] = i
        a["n_songs"] = len(a["songs"])
        a["counted_plays"] = round(a["counted_plays"], 2)
    out["rows"] = [{k: a[k] for k in ("rank", "artist_name", "share", "n_songs", "raw_plays", "counted_plays", "songs")}
                   for a in ranked]
    return out
