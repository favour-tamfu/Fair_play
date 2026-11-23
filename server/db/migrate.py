"""Apply server/db/migrations/*.sql in name order, once each, recorded in schema_migrations.

    python -m server.db.migrate            # uses DATABASE_URL

Safe to call from several services at once: a Postgres advisory lock serialises them, and each file runs in its own
transaction (a failing file leaves nothing half-applied).
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

import psycopg

from server import config
from server.db import connect

log = logging.getLogger(__name__)
MIGRATION_LOCK = 4242


def pending(conn: psycopg.Connection, migrations_dir: Path) -> list[Path]:
    done = {r["version"] for r in conn.execute("SELECT version FROM schema_migrations")}
    return [p for p in sorted(migrations_dir.glob("*.sql")) if p.stem not in done]


def migrate(url: Optional[str] = None, migrations_dir: Path = config.MIGRATIONS_DIR) -> list[str]:
    """Apply pending migrations; return the versions applied now."""
    applied: list[str] = []
    with connect(url, autocommit=True) as conn:
        conn.execute("SELECT pg_advisory_lock(%s)", (MIGRATION_LOCK,))
        try:
            conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations "
                         "(version text PRIMARY KEY, applied_at timestamptz DEFAULT now())")
            for path in pending(conn, migrations_dir):
                with conn.transaction():
                    conn.execute(path.read_text(encoding="utf-8"))
                    conn.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (path.stem,))
                applied.append(path.stem)
                log.info("migration applied: %s", path.stem)
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (MIGRATION_LOCK,))
    return applied


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    done = migrate()
    print(f"applied: {done or 'nothing (up to date)'}")
    sys.exit(0)
