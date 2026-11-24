"""Ledger auditor (brief §8): recompute the hash chain and every anchor from what is in the database NOW.

A row is intact if its stored prev_chain_hash equals the previous row's recomputed hash AND its stored chain_hash
equals sha256(prev ‖ canonical(core fields as stored now)). Editing any core field of any play (e.g. the tamper
tool changing song_id) breaks that row → intact=false, broken_at_play_id = the first broken play.
Each anchor is re-checked against the first n_plays of its hour. Speed: a cheap SQL fingerprint of all core fields
is compared with the last audited one; the full Python recomputation only runs when something changed.
"""
from __future__ import annotations

import time
from typing import Any, Optional

import psycopg

from fairplay_core.schema import format_utc
from server.ledger import chain
from server.ledger.anchor import hour_hashes
from server.ledger.merkle import merkle_root

FINGERPRINT_SQL = """
SELECT count(*) AS n, md5(string_agg(concat_ws('|', chain, seq_no, play_id, meter_id, venue_id, song_id, started_at,
       duration_s, n_windows, prev_chain_hash, chain_hash), ',' ORDER BY chain, seq_no)) AS fp FROM plays
"""
_cache: dict[str, Any] = {"key": None, "result": None}


def _anchor_out(a: Optional[dict]) -> Optional[dict]:
    if not a:
        return None
    return {"hour": format_utc(a["hour"]), "root": a["root"], "via": a["via"], "tx_ref": a["tx_ref"]}


def full_audit(conn: psycopg.Connection) -> dict[str, Any]:
    broken: Optional[str] = None
    prev = chain.GENESIS
    n = 0
    with conn.cursor() as cur:
        cur.execute("SELECT chain, play_id, meter_id, venue_id, song_id, started_at, duration_s, n_windows, "
                    "prev_chain_hash, chain_hash FROM plays ORDER BY chain, seq_no")
        current = None
        for row in cur:
            if row["chain"] != current:        # D-013: each chain (live, mock) starts from its own genesis
                current, prev = row["chain"], chain.GENESIS
            n += 1
            expected = chain.link(prev, row)
            if broken is None and (row["prev_chain_hash"] != prev or row["chain_hash"] != expected):
                broken = row["play_id"]
            prev = expected                    # keep walking with the RECOMPUTED chain
    anchors = conn.execute("SELECT * FROM anchors ORDER BY hour").fetchall()
    anchors_ok = True
    for a in anchors:
        if merkle_root(hour_hashes(conn, a["hour"], a["n_plays"])) != a["root"]:
            anchors_ok = False
    last = anchors[-1] if anchors else None
    return {"intact": broken is None and anchors_ok, "broken_at_play_id": broken, "plays_checked": n,
            "last_root": last["root"] if last else None, "last_anchor": _anchor_out(last)}


def status(conn: psycopg.Connection) -> dict[str, Any]:
    """Audit result, recomputed only if any play row or anchor changed since the last audit."""
    fp = conn.execute(FINGERPRINT_SQL).fetchone()
    an = conn.execute("SELECT count(*) AS n, md5(string_agg(concat_ws('|', hour, root, n_plays), ',' ORDER BY hour)) "
                      "AS fp FROM anchors").fetchone()
    key = (fp["n"], fp["fp"], an["n"], an["fp"])
    if _cache["key"] != key:
        t0 = time.perf_counter()
        _cache["result"] = full_audit(conn)
        _cache["result"]["_audit_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        _cache["key"] = key
    return {k: v for k, v in _cache["result"].items() if not k.startswith("_")}
