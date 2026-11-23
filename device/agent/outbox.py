"""Outbox (A-T05): signed batches wait here on disk until the server acks them.

Lives in the same SQLite file as MeterState (device/state/<meter>.db):
  outbox(seq PK, json, created_at, attempts, last_error)   batches waiting to be sent
  dead(seq PK, json, reason, moved_at)                     batches the server will never accept
Rows are removed only after an ack (ack) or a move to dead (to_dead), never before.
"""
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from typing import List, Tuple


class Outbox:
    def __init__(self, path: str):
        self.path = path
        with closing(sqlite3.connect(path)) as con, con:
            con.execute(
                "CREATE TABLE IF NOT EXISTS outbox ("
                " seq INTEGER PRIMARY KEY, json TEXT NOT NULL, created_at TEXT,"
                " attempts INTEGER DEFAULT 0, last_error TEXT)"
            )
            con.execute(
                "CREATE TABLE IF NOT EXISTS dead ("
                " seq INTEGER PRIMARY KEY, json TEXT, reason TEXT, moved_at TEXT)"
            )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def put(self, batch: dict) -> None:
        with closing(sqlite3.connect(self.path, timeout=10)) as con, con:
            con.execute(
                "INSERT OR REPLACE INTO outbox (seq, json, created_at, attempts, last_error) VALUES (?, ?, ?, 0, NULL)",
                (int(batch["seq"]), json.dumps(batch, sort_keys=True), self._now()),
            )

    def peek(self, n: int, exclude=None) -> List[Tuple[int, dict, int]]:
        """Oldest first: list of (seq, batch, attempts). Seqs in `exclude` are skipped."""
        skip = sorted({int(s) for s in (exclude or ())})
        with closing(sqlite3.connect(self.path, timeout=10)) as con:
            if skip:
                marks = ",".join("?" * len(skip))
                rows = con.execute(
                    f"SELECT seq, json, attempts FROM outbox WHERE seq NOT IN ({marks}) ORDER BY seq LIMIT ?",
                    (*skip, int(n)),
                ).fetchall()
            else:
                rows = con.execute(
                    "SELECT seq, json, attempts FROM outbox ORDER BY seq LIMIT ?", (int(n),)
                ).fetchall()
        return [(seq, json.loads(js), att) for seq, js, att in rows]

    def ack(self, seq: int) -> None:
        with closing(sqlite3.connect(self.path, timeout=10)) as con, con:
            con.execute("DELETE FROM outbox WHERE seq = ?", (int(seq),))

    def record_error(self, seq: int, error: str) -> None:
        with closing(sqlite3.connect(self.path, timeout=10)) as con, con:
            con.execute(
                "UPDATE outbox SET attempts = attempts + 1, last_error = ? WHERE seq = ?",
                (error, int(seq)),
            )

    def to_dead(self, seq: int, reason: str) -> None:
        with closing(sqlite3.connect(self.path, timeout=10)) as con, con:
            con.execute(
                "INSERT OR REPLACE INTO dead (seq, json, reason, moved_at) "
                "SELECT seq, json, ?, ? FROM outbox WHERE seq = ?",
                (reason, self._now(), int(seq)),
            )
            con.execute("DELETE FROM outbox WHERE seq = ?", (int(seq),))

    def count(self) -> int:
        with closing(sqlite3.connect(self.path, timeout=10)) as con:
            (n,) = con.execute("SELECT COUNT(*) FROM outbox").fetchone()
        return int(n)

    def dead_count(self) -> int:
        with closing(sqlite3.connect(self.path, timeout=10)) as con:
            (n,) = con.execute("SELECT COUNT(*) FROM dead").fetchone()
        return int(n)
