"""Which plays belong to a period — shared by the read API and stats runs (one definition, PLAN_B B-T08).

  live       = plays from live/virtual meters since config.LIVE_SINCE
  mock_month = plays imported from A's mock month (source mock, B-T11)
  all        = everything
Plays superseded by a correction ('not_confirmed_on_recompute') are never shown or counted.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fairplay_core.schema import parse_utc
from server import config

PERIODS = ("live", "mock_month", "all")
ACTIVE = "NOT EXISTS (SELECT 1 FROM play_corrections c WHERE c.play_id = p.play_id AND c.reason = 'not_confirmed_on_recompute')"


def period_sql(period: str) -> tuple[str, list]:
    if period == "live":
        return "p.source IN ('live','virtual') AND p.started_at >= %s", [parse_utc(config.LIVE_SINCE)]
    if period == "mock_month":
        return "p.source = 'mock'", []
    if period == "all":
        return "true", []
    raise ValueError(f"unknown period {period!r}")


def period_bounds(conn, period: str) -> tuple[datetime, datetime]:
    """[start, end) of the period: live = LIVE_SINCE -> now; otherwise first play start -> last play end."""
    now = datetime.now(timezone.utc)
    if period == "live":
        return parse_utc(config.LIVE_SINCE), now
    where, args = period_sql(period)
    r = conn.execute(f"""SELECT min(p.started_at) AS a,
                                max(COALESCE(x.ended_at, p.started_at + make_interval(secs => COALESCE(p.duration_s, 0)))) AS b
                         FROM plays p LEFT JOIN play_extents x USING (play_id) WHERE {where}""", args).fetchone()
    if r["a"] is None:
        return now, now
    return r["a"], max(r["b"], r["a"] + timedelta(seconds=1))
