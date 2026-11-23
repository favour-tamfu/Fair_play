"""Server settings — one place for every tunable number. Read from environment variables where it matters.

Rule thresholds for stats (B-T09) are added here when those tasks are built.
"""
from __future__ import annotations

import os
from pathlib import Path

VERSION = "0.1.0"

ROOT = Path(__file__).resolve().parents[1]          # /app in the container, repo root on the host
CONTRACT_DIR = ROOT / "contract"
METERS_DIR = CONTRACT_DIR / "meters"
SCHEMAS_DIR = CONTRACT_DIR / "schemas"
WEB_DIR = ROOT / "web"
MEDIA_DIR = ROOT / "media"
SONGS_DIR = MEDIA_DIR / "songs"
ANCHORS_DIR = ROOT / "server" / "anchors"
MIGRATIONS_DIR = ROOT / "server" / "db" / "migrations"

def _from_dotenv(key: str) -> str | None:
    """Read KEY=value from the repo's .env (host-side tools/tests; containers get env vars from compose)."""
    env = ROOT / ".env"
    if not env.exists():
        return None
    for line in env.read_text(encoding="utf-8").splitlines():
        k, sep, v = line.partition("=")
        if sep and k.strip() == key and not line.lstrip().startswith("#"):
            return v.strip()
    return None


# Inside docker compose DATABASE_URL points at host "db"; on the host it comes from .env (published port 55432).
DATABASE_URL = (os.environ.get("DATABASE_URL") or _from_dotenv("DATABASE_URL")
                or "postgresql://fairplay:fairplay@127.0.0.1:55432/fairplay")

# Workers
JOB_POLL_S = 0.5                 # how often an idle worker checks the job board
WORKER_IDLE_LOG_S = 300          # placeholder workers log "alive" this often
