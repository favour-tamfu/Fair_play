"""Public anchors (brief §8): publish each hour's Merkle root somewhere SONACAM cannot quietly rewrite.

FileAnchor (default): append one JSON line to server/anchors/anchors.jsonl — shown in the Trust tab.
SepoliaAnchor (B-T15, stretch) will send a 0-value testnet transaction with the root in `data`.

anchor_hour(conn, hour) computes the root of the first n plays inserted in that hour (by seq_no) and stores
anchors(hour, root, n_plays, via, tx_ref). An hour can be re-anchored on demand while it is still open (more plays
arrived); the auditor always re-checks a stored anchor against the same first n_plays, so earlier anchors stay valid.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import psycopg

from fairplay_core.schema import format_utc
from server import config
from server.ledger.merkle import merkle_root

log = logging.getLogger(__name__)


class FileAnchor:
    via = "file"

    def __init__(self, path: Optional[Path] = None):
        self.path = path or (config.ANCHORS_DIR / "anchors.jsonl")

    def publish(self, hour: datetime, root: str, n_plays: int) -> Optional[str]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = {"hour": format_utc(hour), "root": root, "n_plays": n_plays, "via": self.via,
                "published_at": format_utc(datetime.now(timezone.utc))}
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(line) + "\n")
        return None   # a file has no transaction reference


def get_anchor() -> FileAnchor:
    return FileAnchor()


def hour_hashes(conn: psycopg.Connection, hour: datetime, limit: Optional[int] = None) -> list[str]:
    sql = ("SELECT chain_hash FROM plays WHERE chain = 'live' AND inserted_at >= %s AND inserted_at < %s AND chain_hash IS NOT NULL "
           "ORDER BY seq_no")
    args: list = [hour, hour + timedelta(hours=1)]
    if limit is not None:
        sql += " LIMIT %s"
        args.append(limit)
    return [r["chain_hash"] for r in conn.execute(sql, args)]


def anchor_hour(conn: psycopg.Connection, hour: datetime, anchor=None) -> Optional[dict]:
    """Anchor one hour (UTC, truncated). Returns the anchors row, or None if the hour had no plays."""
    hour = hour.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
    hashes = hour_hashes(conn, hour)
    root = merkle_root(hashes)
    if root is None:
        return None
    prev = conn.execute("SELECT * FROM anchors WHERE hour = %s", (hour,)).fetchone()
    if prev and prev["root"] == root and prev["n_plays"] == len(hashes):
        return prev                                   # nothing new in this hour
    anchor = anchor or get_anchor()
    tx_ref = anchor.publish(hour, root, len(hashes))
    row = conn.execute(
        """INSERT INTO anchors (hour, root, n_plays, via, tx_ref) VALUES (%s, %s, %s, %s, %s)
           ON CONFLICT (hour) DO UPDATE SET root = EXCLUDED.root, n_plays = EXCLUDED.n_plays, via = EXCLUDED.via,
               tx_ref = EXCLUDED.tx_ref, created_at = now()
           RETURNING *""", (hour, root, len(hashes), anchor.via, tx_ref)).fetchone()
    log.info("anchored %s: %d plays, root %s… via %s", format_utc(hour), len(hashes), root[:12], anchor.via)
    return row


def anchor_closed_hours(conn: psycopg.Connection, now: Optional[datetime] = None) -> list[dict]:
    """Anchor every finished hour that has plays but no (up-to-date) anchor yet."""
    now = now or datetime.now(timezone.utc)
    current = now.replace(minute=0, second=0, microsecond=0)
    hours = conn.execute(
        """SELECT date_trunc('hour', inserted_at) AS hour, count(*) AS n FROM plays
           WHERE chain = 'live' AND inserted_at < %s AND chain_hash IS NOT NULL GROUP BY 1 ORDER BY 1""", (current,)).fetchall()
    done = {r["hour"]: r["n_plays"] for r in conn.execute("SELECT hour, n_plays FROM anchors")}
    out = []
    for h in hours:
        if done.get(h["hour"]) != h["n"]:
            row = anchor_hour(conn, h["hour"])
            if row:
                out.append(row)
    return out
