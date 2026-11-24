"""Tamper-evident play log (brief §8): every play row carries chain_hash = sha256(prev_chain_hash ‖ canonical(core)).

core fields (fixed at confirmation, never updated): play_id, meter_id, venue_id, song_id, started_at (UTC ms Z),
duration_s (rounded to 0.1), n_windows. The first play links to 64 zeros. `append` must run in the SAME transaction
as the play insert; an advisory lock serialises writers so the chain never forks.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

import psycopg

from fairplay_core.schema import format_utc

GENESIS = "0" * 64
CHAIN_LOCK = 42


def core_fields(play: dict[str, Any]) -> dict[str, Any]:
    started = play["started_at"]
    return {"play_id": play["play_id"], "meter_id": play["meter_id"], "venue_id": play["venue_id"],
            "song_id": play["song_id"], "started_at": started if isinstance(started, str) else format_utc(started),
            "duration_s": round(float(play["duration_s"]), 1), "n_windows": int(play["n_windows"])}


def canonical(play: dict[str, Any]) -> str:
    return json.dumps(core_fields(play), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def link(prev: str, play: dict[str, Any]) -> str:
    return hashlib.sha256((prev + canonical(play)).encode("utf-8")).hexdigest()


def append(conn: psycopg.Connection, play: dict[str, Any], chain: str = "live") -> tuple[str, str]:
    """Return (prev_chain_hash, chain_hash) for a play about to be inserted (caller inserts both, with this chain).

    D-013: chains are namespaced (plays.chain): "live" (meters, never wiped) and "mock" (mock month import).
    """
    conn.execute("SELECT pg_advisory_xact_lock(%s)", (CHAIN_LOCK,))
    row = conn.execute("SELECT chain_hash FROM plays WHERE chain = %s ORDER BY seq_no DESC LIMIT 1", (chain,)).fetchone()
    prev = row["chain_hash"] if row and row["chain_hash"] else GENESIS
    return prev, link(prev, play)
