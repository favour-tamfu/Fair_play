"""Ledger auditor (brief §8): recompute the hash chain and every anchor from what is in the database NOW.

A row is intact if its stored prev_chain_hash equals the previous row's recomputed hash AND its stored chain_hash
equals sha256(prev ‖ canonical(core fields as stored now)). Editing any core field of any play (e.g. the tamper
tool changing song_id) breaks that row → intact=false, broken_at_play_id = the first broken play.
Each anchor (live chain, current epoch) is re-checked against the first n_plays of its hour.

Speed (B-T13): one SQL fingerprint per chain (≈ 0.1 s for 65 000 plays); a chain is re-walked in Python only when
ITS fingerprint changed. Tampering with a live play re-walks the live chain only (milliseconds), not the
mock month's 65 000 plays (≈ 1.7 s), so the scheduler's 2 s ledger check reports it within 2 s.
"""
from __future__ import annotations

import time
from typing import Any, Optional

import psycopg

from fairplay_core.schema import format_utc
from server.ledger import chain
from server.ledger.anchor import hour_hashes
from server.ledger.merkle import merkle_root

COLS = "seq_no, play_id, meter_id, venue_id, song_id, started_at, duration_s, n_windows, prev_chain_hash, chain_hash"
FINGERPRINT_SQL = f"""
SELECT chain, count(*) AS n, md5(string_agg(concat_ws('|', {COLS}), ',' ORDER BY seq_no)) AS fp FROM plays GROUP BY chain
"""
ANCHORS_SQL = ("SELECT count(*) AS n, md5(string_agg(concat_ws('|', hour, root, n_plays), ',' ORDER BY hour)) AS fp "
               "FROM anchors")
_cache: dict[str, Any] = {}          # chain -> (fingerprint, {"broken", "n"}); "anchors" -> (fingerprint, result)


def _anchor_out(a: Optional[dict]) -> Optional[dict]:
    if not a:
        return None
    return {"hour": format_utc(a["hour"]), "root": a["root"], "via": a["via"], "tx_ref": a["tx_ref"]}


def audit_chain(conn: psycopg.Connection, name: str) -> dict[str, Any]:
    """Walk one chain from its own genesis (D-013)."""
    broken: Optional[str] = None
    prev = chain.GENESIS
    n = 0
    with conn.cursor() as cur:
        cur.execute("SELECT play_id, meter_id, venue_id, song_id, started_at, duration_s, n_windows, prev_chain_hash, "
                    "chain_hash FROM plays WHERE chain = %s ORDER BY seq_no", (name,))
        for row in cur:
            n += 1
            expected = chain.link(prev, row)
            if broken is None and (row["prev_chain_hash"] != prev or row["chain_hash"] != expected):
                broken = row["play_id"]
            prev = expected                    # keep walking with the RECOMPUTED chain
    return {"broken": broken, "n": n}


def audit_anchors(conn: psycopg.Connection) -> dict[str, Any]:
    anchors = conn.execute("SELECT * FROM anchors ORDER BY hour").fetchall()
    ok = all(merkle_root(hour_hashes(conn, a["hour"], a["n_plays"])) == a["root"] for a in anchors)
    return {"ok": ok, "last": anchors[-1] if anchors else None}


def _combine(chains: dict[str, dict], anchors: dict) -> dict[str, Any]:
    order = sorted(chains, key=lambda c: (c != "live", c))           # live first: the demo's chain
    broken = next((chains[c]["broken"] for c in order if chains[c]["broken"]), None)
    last = anchors["last"]
    return {"intact": broken is None and anchors["ok"], "broken_at_play_id": broken,
            "plays_checked": sum(c["n"] for c in chains.values()),
            "last_root": last["root"] if last else None, "last_anchor": _anchor_out(last)}


def full_audit(conn: psycopg.Connection) -> dict[str, Any]:
    """Everything recomputed, no cache (tests, tools)."""
    names = [r["chain"] for r in conn.execute("SELECT DISTINCT chain FROM plays")]
    return _combine({c: audit_chain(conn, c) for c in names}, audit_anchors(conn))


def status(conn: psycopg.Connection) -> dict[str, Any]:
    """Audit result; a chain (or the anchors) is recomputed only if its fingerprint changed since the last audit."""
    chains = {}
    for r in conn.execute(FINGERPRINT_SQL).fetchall():
        key = (r["n"], r["fp"])
        hit = _cache.get(("chain", r["chain"]))
        if hit is None or hit[0] != key:
            t0 = time.perf_counter()
            hit = (key, audit_chain(conn, r["chain"]))
            hit[1]["_ms"] = round((time.perf_counter() - t0) * 1000, 1)
            _cache[("chain", r["chain"])] = hit
        chains[r["chain"]] = hit[1]
    for k in [k for k in _cache if k[0] == "chain" and k[1] not in chains]:
        del _cache[k]                                                  # a chain that no longer exists
    an = conn.execute(ANCHORS_SQL).fetchone()
    # anchors depend on the live chain too (hour_hashes), so their key includes the live fingerprint
    akey = (an["n"], an["fp"], _cache.get(("chain", "live"), (None,))[0])
    hit = _cache.get("anchors")
    if hit is None or hit[0] != akey:
        hit = (akey, audit_anchors(conn))
        _cache["anchors"] = hit
    return _combine(chains, hit[1])
