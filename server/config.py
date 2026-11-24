"""Server settings â€” one place for every tunable number. Read from environment variables where it matters.

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

# Catalogue (B-T04, contract Â§5)
UPLOAD_MAX_BYTES = 50 * 1024 * 1024   # c-1.1 (PROPOSED 2026-11-24): was 30 MB in c-1.0
UPLOAD_EXTENSIONS = {".mp3", ".wav", ".m4a", ".flac"}
DUP_SLICES = (0.2, 0.5, 0.8)     # duplicate check: 10 s slices at 20 %, 50 %, 80 % of the new song (brief Â§5.4)
DUP_MIN_HITS = 2                 # â‰¥ 2 slices matching the same existing song â†’ duplicate_suspected
# Catalogue-side only (device and fp-1.0 unchanged): index each song on several frame-grid phases (in samples at
# 8 kHz). A meter window starts at a random point, up to half a hop (128 samples) off a single grid, which weakens
# its votes; a second grid shifted by half a hop halves that worst case. Hashes of a shifted grid are stored with
# the frame index of that grid (â‰¤ 16 ms early), which the Â±1-frame vote tolerance absorbs. (DECISIONS D-006)
FP_INDEX_SHIFTS = (0, 128)
WORKER_IDLE_LOG_S = 300          # placeholder workers log "alive" this often

# Play logger (B-T06, brief Â§6)
SAME_PLAY_TOL_S = 5.0            # |Î”offset âˆ’ Î”time| â‰¤ 5 s â†’ same play
RESTART_BACK_S = 20.0            # offset jumped back > 20 s â†’ new play
RESTART_GAP_EXTRA_S = 60.0       # gap > (song_length âˆ’ last_offset) + 60 s â†’ new play
CONFIRM_MIN_WINDOWS = 2          # confirmed play: â‰¥ 2 accepted windows â€¦
CONFIRM_MIN_COVER_S = 30.0       # â€¦ and covered â‰¥ min(30 s, 0.3 Ã— song length)
CONFIRM_MIN_COVER_FRAC = 0.3
DEFAULT_SONG_LENGTH_S = 240.0    # if a song's duration is unknown
MUSIC_LOUDNESS_DB = -35.0        # unmatched window louder than this = "music, unidentified"
LOCAL_UTC_OFFSET_H = 1           # Cameroon (Africa/Douala) = UTC+1, no DST
VENUE_DAY_START_H = 6            # a venue-night runs 06:00 â†’ 06:00 local (so 18:00â€“02:00 is one night)

# Ledger + scheduler (B-T07)
LEDGER_CHECK_S = 1.0             # auditor runs this often; dashboard turns red well within 2 s of a tamper
METER_OFFLINE_S = 150            # no batch/heartbeat for this long â†’ meter offline (field mode sends every 60 s)

# Read API (B-T08)
RULE_VERSION = "sr-1.0"
POT_DEFAULT_FCFA = 100_000_000   # "bar levy pot (example)"
# period=live: live/virtual plays since the build started (Mon 23 Nov 12:00 local = 11:00 UTC)
LIVE_SINCE = os.environ.get("LIVE_SINCE", "2026-11-23T11:00:00.000Z")
# Venue details known in advance (contract §7); fill only EMPTY fields at start-up, never overwrite imported data
KNOWN_VENUES = {
    "V-BUEA-CIMFEST": {"name": "CIMFEST demo table", "city": "Buea", "lat": 4.1527, "lon": 9.2410,
                       "size_class": "S", "stratum": "BUEA-S"},
}
