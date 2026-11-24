"""Demo reset (B-T13, D-017): wipe the LIVE test data before a demo run; keep the catalogue, meters, mock month.

    reset_live(conn, reason="demo reset") -> {"epoch", "plays_removed", ...}

Removed: live/virtual batches, match events, windows, plays of chain 'live' (+ extents, corrections, weights),
stats runs of period 'live' (+ shares, weights, flags), match/play jobs, playlogger state.
Kept: songs + hashes, owners, venues, meters (keys, last_seq: a meter re-sending an old seq is simply stored again),
the mock month (chain 'mock', mock tables), catalogue flags (duplicate_suspected).
Ledger: the live chain restarts from genesis in a new epoch. The previous epoch's anchors move to anchors_archive
and a line {"event": "epoch", ...} is appended to the public anchors file, so the reset itself is on record.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import psycopg

from fairplay_core.schema import format_utc
from server import config
from server.ledger import audit, chain
from server.stats.run import LOCK as STATS_LOCK

log = logging.getLogger("demo")


def reset_live(conn: psycopg.Connection, reason: str = "demo reset") -> dict:
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (chain.CHAIN_LOCK,))
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (STATS_LOCK,))
        live = "SELECT play_id FROM plays WHERE chain = 'live'"
        last = conn.execute("SELECT chain_hash FROM plays WHERE chain = 'live' ORDER BY seq_no DESC LIMIT 1").fetchone()
        n_plays = conn.execute("SELECT count(*) AS n FROM plays WHERE chain = 'live'").fetchone()["n"]
        runs = [r["stats_run_id"] for r in conn.execute("SELECT stats_run_id FROM stats_runs WHERE period = 'live'")]
        for t in ("play_weights", "shares", "flags", "stats_runs"):
            conn.execute(f"DELETE FROM {t} WHERE stats_run_id = ANY(%s)", (runs,))
        for t in ("play_weights", "play_corrections", "play_extents"):
            conn.execute(f"DELETE FROM {t} WHERE play_id IN ({live})")
        conn.execute("DELETE FROM plays WHERE chain = 'live'")
        counts = {"plays_removed": n_plays,
                  "batches_removed": conn.execute("DELETE FROM raw_batches").rowcount,
                  "match_events_removed": conn.execute("DELETE FROM match_events").rowcount,
                  "windows_removed": conn.execute("DELETE FROM windows WHERE source IS DISTINCT FROM 'mock'").rowcount,
                  "jobs_removed": conn.execute("DELETE FROM jobs WHERE kind IN ('match', 'play')").rowcount}
        conn.execute("DELETE FROM playlogger_state")
        conn.execute("UPDATE meters SET queued = 0 WHERE source <> 'mock'")
        epoch = conn.execute("""INSERT INTO ledger_epochs (reason, plays_removed, last_root)
                                VALUES (%s, %s, %s) RETURNING epoch, started_at""",
                             (reason, n_plays, last["chain_hash"] if last else None)).fetchone()
        conn.execute("""INSERT INTO anchors_archive (epoch, hour, root, n_plays, via, tx_ref, created_at)
                        SELECT %s - 1, hour, root, n_plays, via, tx_ref, created_at FROM anchors WHERE chain = 'live'""",
                     (epoch["epoch"],))
        counts["anchors_archived"] = conn.execute("DELETE FROM anchors WHERE chain = 'live'").rowcount
    _publish_epoch(epoch["epoch"], epoch["started_at"], reason, n_plays, last["chain_hash"] if last else None)
    audit._cache.clear()
    out = {"ok": True, "epoch": epoch["epoch"], "started_at": format_utc(epoch["started_at"]), "reason": reason, **counts}
    log.warning("DEMO RESET: %s", out)
    return out


def _publish_epoch(epoch: int, started: datetime, reason: str, n: int, last_root) -> None:
    path = config.ANCHORS_DIR / "anchors.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    line = {"event": "epoch", "epoch": epoch, "reason": reason, "plays_removed": n, "last_chain_hash": last_root,
            "published_at": format_utc(started.astimezone(timezone.utc))}
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(line) + "\n")
