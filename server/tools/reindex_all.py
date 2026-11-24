"""Re-fingerprint every indexed upload (needed only if fingerprint parameters ever change — docs/02 §6 rule 5).

    python -m server.tools.reindex_all            # queue jobs; the fingerprint worker does the work

Songs that are ready / failed / processing are re-queued with mode "reindex" (no duplicate check, so approved
duplicates stay indexed). duplicate_suspected songs are left for an admin decision.
"""
from __future__ import annotations

from server.db import connect, jobs


def main() -> int:
    with connect(autocommit=True) as conn, conn.transaction():
        rows = conn.execute("SELECT song_id FROM songs WHERE source = 'upload' AND status IN "
                            "('ready', 'failed', 'processing', 'uploaded') ORDER BY song_id").fetchall()
        for r in rows:
            conn.execute("UPDATE songs SET status = 'uploaded' WHERE song_id = %s", (r["song_id"],))
            jobs.enqueue(conn, "fingerprint", f"{r['song_id']}:reindex")
    print(f"queued {len(rows)} songs for re-fingerprinting")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
