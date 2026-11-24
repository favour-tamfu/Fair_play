"""Scheduler ("the night guard"): small periodic duties, one loop.

  every 2 s   ledger audit; when intact / broken_at changes → NOTIFY "ledger" {"intact","broken_at_play_id"}
  every 10 s  meters online/offline (last_seen older than METER_OFFLINE_S) → NOTIFY "meter" when it flips
  every 60 s  anchor every finished hour that has plays (FileAnchor)
(stats every 5 min are added in B-T10)
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import psycopg

from fairplay_core.schema import format_utc
from server import config
from server.db import connect, notify
from server.ledger import audit
from server.ledger.anchor import anchor_closed_hours

log = logging.getLogger("scheduler")


class Scheduler:
    def __init__(self) -> None:
        self.ledger_state = None              # (intact, broken_at) last announced
        self.online: dict[str, bool] = {}
        self.due = {"ledger": 0.0, "meters": 0.0, "anchors": 0.0}

    def check_ledger(self, conn: psycopg.Connection) -> dict:
        s = audit.status(conn)
        state = (s["intact"], s["broken_at_play_id"])
        if state != self.ledger_state:
            notify(conn, "ledger", {"intact": s["intact"], "broken_at_play_id": s["broken_at_play_id"]})
            (log.info if s["intact"] else log.error)("ledger %s (broken at %s, %d plays)",
                                                     "INTACT" if s["intact"] else "BROKEN", s["broken_at_play_id"],
                                                     s["plays_checked"])
            self.ledger_state = state
        return s

    def check_meters(self, conn: psycopg.Connection, now: datetime) -> list[str]:
        flipped = []
        for m in conn.execute("SELECT meter_id, last_seen, queued FROM meters WHERE source <> 'mock'"):
            online = m["last_seen"] is not None and (now - m["last_seen"]).total_seconds() <= config.METER_OFFLINE_S
            if self.online.get(m["meter_id"]) is not None and self.online[m["meter_id"]] != online:
                notify(conn, "meter", {"meter_id": m["meter_id"], "online": online, "queued": m["queued"] or 0,
                                       "last_seen": format_utc(m["last_seen"]) if m["last_seen"] else None})
                flipped.append(m["meter_id"])
                log.info("meter %s is now %s", m["meter_id"], "ONLINE" if online else "OFFLINE")
            self.online[m["meter_id"]] = online
        return flipped

    def tick(self, conn: psycopg.Connection) -> None:
        t = time.monotonic()
        now = datetime.now(timezone.utc)
        if t >= self.due["ledger"]:
            self.check_ledger(conn)
            self.due["ledger"] = t + config.LEDGER_CHECK_S
        if t >= self.due["meters"]:
            self.check_meters(conn, now)
            self.due["meters"] = t + 10
        if t >= self.due["anchors"]:
            with conn.transaction():
                anchor_closed_hours(conn, now)
            self.due["anchors"] = t + 60


def main() -> None:
    from server.workers.base import setup
    setup("scheduler")
    s = Scheduler()
    while True:
        try:
            with connect(autocommit=True) as conn:
                log.info("scheduler running")
                while True:
                    s.tick(conn)
                    time.sleep(0.5)
        except psycopg.OperationalError as e:
            log.warning("lost the db (%s); reconnecting in 2 s", e)
            time.sleep(2)


if __name__ == "__main__":
    main()
