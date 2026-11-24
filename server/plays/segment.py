"""From match verdicts to plays — brief §6, as a pure function (no database), so it can be tested exhaustively.

Input: one meter's match events in EVENT-TIME order (window_start), each with accepted/song/offset/loudness.
Rules for an accepted window of song s at song offset o heard at time t, against the open play (last_offset, last_t):
  drift = (o − last_offset) − (t − last_t)
  same play            if same song and |drift| ≤ 5 s          (a chorus repeat keeps advancing with the clock)
  new play             if another song, or o jumped BACK > 20 s, or t − last_t > (L − last_offset) + 60 s
  An off-track window of the same song (|drift| > 5 s, not past the song's end) is never acted on alone: it is held
  as "pending" and the NEXT accepted window decides:
      agrees with the open play   → the pending window was a stray (e.g. another copy of a repeated section): ignored
      agrees with the pending one → it was real: jumped BACK > 20 s = the song restarted (new play from the pending
                                    window); otherwise the DJ skipped forward inside the song (same play continues)
  (Deviation from the literal brief, which starts a new play on a single back-jump: one stray window must not split
  a play into two — DECISIONS D-007.)
Confirmed play: ≥ 2 accepted windows and covered ≥ min(30 s, 0.3 × L), covered = last_offset + 10 − first_offset.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable, Optional, Sequence

from server import config

WINDOW_S = 10.0


@dataclass
class Event:
    id: int
    window_start: datetime
    accepted: bool
    song_id: Optional[str]
    offset_s: float
    loudness_db: Optional[float] = None


@dataclass
class Candidate:
    song_id: str
    song_length_s: float
    first_ws: datetime
    first_offset_s: float
    last_ws: datetime
    last_offset_s: float
    event_ids: list[int] = field(default_factory=list)
    loudness: list[float] = field(default_factory=list)

    @property
    def n_windows(self) -> int:
        return len(self.event_ids)

    @property
    def covered_s(self) -> float:
        return self.last_offset_s + WINDOW_S - self.first_offset_s

    @property
    def confirmed(self) -> bool:
        need = min(config.CONFIRM_MIN_COVER_S, config.CONFIRM_MIN_COVER_FRAC * self.song_length_s)
        return self.n_windows >= config.CONFIRM_MIN_WINDOWS and self.covered_s >= need - 1e-6

    @property
    def started_at(self) -> datetime:
        """Wall time the song started = first window − its song offset (never more than one song length back)."""
        back = min(self.first_offset_s, self.song_length_s)
        return self.first_ws - timedelta(seconds=back)

    @property
    def ended_at(self) -> datetime:
        return self.last_ws + timedelta(seconds=WINDOW_S)

    @property
    def duration_s(self) -> float:
        return (self.ended_at - self.started_at).total_seconds()

    @property
    def mean_loudness_db(self) -> Optional[float]:
        return round(sum(self.loudness) / len(self.loudness), 1) if self.loudness else None

    def add(self, e: Event) -> None:
        self.last_ws, self.last_offset_s = e.window_start, e.offset_s
        self.event_ids.append(e.id)
        if e.loudness_db is not None:
            self.loudness.append(e.loudness_db)


def _drift(e: Event, offset: float, t: datetime) -> float:
    return (e.offset_s - offset) - (e.window_start - t).total_seconds()


def segment(events: Sequence[Event], song_length: Callable[[str], float]) -> list[Candidate]:
    """All play candidates (confirmed or not) of one meter, in time order. `events` must be in event-time order."""
    out: list[Candidate] = []
    cur: Optional[Candidate] = None
    pending: Optional[Event] = None

    def start(e: Event) -> Candidate:
        c = Candidate(e.song_id, song_length(e.song_id), e.window_start, e.offset_s, e.window_start, e.offset_s)
        c.event_ids.append(e.id)
        if e.loudness_db is not None:
            c.loudness.append(e.loudness_db)
        out.append(c)
        return c

    for e in events:
        if not e.accepted or not e.song_id:
            continue
        if cur is None or e.song_id != cur.song_id:
            cur, pending = start(e), None
            continue
        gap = (e.window_start - cur.last_ws).total_seconds()
        remaining = max(0.0, cur.song_length_s - cur.last_offset_s)    # never negative if the stored length is short
        if gap > remaining + config.RESTART_GAP_EXTRA_S:
            cur, pending = start(e), None                          # song would have ended long ago → replayed
            continue
        if abs(_drift(e, cur.last_offset_s, cur.last_ws)) <= config.SAME_PLAY_TOL_S:
            cur.add(e)                                             # on track; a pending window was a stray
            pending = None
            continue
        if pending is not None and abs(_drift(e, pending.offset_s, pending.window_start)) <= config.SAME_PLAY_TOL_S:
            # two windows agree on a new position: real, not a stray
            if pending.offset_s < cur.last_offset_s - config.RESTART_BACK_S:
                cur = start(pending)                               # jumped back > 20 s → the song restarted
                cur.add(e)
            else:
                cur.add(pending)                                   # skipped forward inside the same song
                cur.add(e)
            pending = None
            continue
        pending = e                                                # off-track: hold one window and decide later
    return out
