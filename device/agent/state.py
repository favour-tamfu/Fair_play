"""Persistent per-meter state (A-T03): the batch sequence number survives restarts.

SQLite file: device/state/<meter_id>.db, table meta(key TEXT PRIMARY KEY, value TEXT).
next_seq() commits the new value before the caller builds the batch, so a crash can
skip a number but never reuse one (contract: seq strictly increasing per meter).
"""
import os
import sqlite3
from contextlib import closing

STATE_DIR = os.path.join("device", "state")


class MeterState:
    def __init__(self, meter_id: str, state_dir: str = STATE_DIR):
        os.makedirs(state_dir, exist_ok=True)
        self.path = os.path.join(state_dir, f"{meter_id}.db")
        with closing(sqlite3.connect(self.path)) as con, con:
            con.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
            con.execute("INSERT OR IGNORE INTO meta (key, value) VALUES ('last_seq', '0')")

    def next_seq(self) -> int:
        """Atomically increment and persist last_seq; return the new value (>= 1)."""
        with closing(sqlite3.connect(self.path, isolation_level=None)) as con:
            con.execute("BEGIN IMMEDIATE")
            try:
                (value,) = con.execute("SELECT value FROM meta WHERE key = 'last_seq'").fetchone()
                new = int(value) + 1
                con.execute("UPDATE meta SET value = ? WHERE key = 'last_seq'", (str(new),))
                con.execute("COMMIT")
            except Exception:
                con.execute("ROLLBACK")
                raise
        return new

    def last_seq(self) -> int:
        with closing(sqlite3.connect(self.path)) as con:
            (value,) = con.execute("SELECT value FROM meta WHERE key = 'last_seq'").fetchone()
        return int(value)
