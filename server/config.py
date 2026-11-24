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
SERVE_WEB = os.environ.get("SERVE_WEB", "1") != "0"   # 0: the api serves the API only (dashboard pages off)
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
# D-020: admin actions need the header X-Admin-Token: <ADMIN_TOKEN>; empty = open (dev laptops, tests)
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN") or _from_dotenv("ADMIN_TOKEN") or ""
DATABASE_URL = (os.environ.get("DATABASE_URL") or _from_dotenv("DATABASE_URL")
                or "postgresql://fairplay:fairplay@127.0.0.1:55432/fairplay")

# Workers
JOB_POLL_S = 0.5                 # how often an idle worker checks the job board

# Catalogue (B-T04, contract §5)
UPLOAD_MAX_BYTES = 50 * 1024 * 1024   # c-1.1 (PROPOSED 2026-11-24): was 30 MB in c-1.0
UPLOAD_EXTENSIONS = {".mp3", ".wav", ".m4a", ".flac"}
DUP_SLICES = (0.2, 0.5, 0.8)     # duplicate check: 10 s slices at 20 %, 50 %, 80 % of the new song (brief §5.4)
DUP_MIN_HITS = 2                 # ≥ 2 slices matching the same existing song → duplicate_suspected
DUP_ALIGN_TOL_S = 3.0            # ... and in line: (offset in old song − slice start) agrees within 3 s
# Catalogue-side only (device and fp-1.0 unchanged): index each song on several frame-grid phases (in samples at
# 8 kHz). A meter window starts at a random point, up to half a hop (128 samples) off a single grid, which weakens
# its votes; a second grid shifted by half a hop halves that worst case. Hashes of a shifted grid are stored with
# the frame index of that grid (≤ 16 ms early), which the ±1-frame vote tolerance absorbs. (DECISIONS D-006)
FP_INDEX_SHIFTS = (0, 128)
WORKER_IDLE_LOG_S = 300          # placeholder workers log "alive" this often

# Play logger (B-T06, brief §6)
SAME_PLAY_TOL_S = 5.0            # |Δoffset − Δtime| ≤ 5 s → same play
RESTART_BACK_S = 20.0            # offset jumped back > 20 s → new play
RESTART_GAP_EXTRA_S = 60.0       # gap > (song_length − last_offset) + 60 s → new play
CONFIRM_MIN_WINDOWS = 2          # confirmed play: ≥ 2 accepted windows …
CONFIRM_MIN_COVER_S = 30.0       # … and covered ≥ min(30 s, 0.3 × song length)
CONFIRM_MIN_COVER_FRAC = 0.3
DEFAULT_SONG_LENGTH_S = 240.0    # if a song's duration is unknown
LOCAL_UTC_OFFSET_H = 1           # Cameroon (Africa/Douala) = UTC+1, no DST
VENUE_DAY_START_H = 6            # a venue-night runs 06:00 → 06:00 local (so 18:00–02:00 is one night)

# Ledger + scheduler (B-T07)
LEDGER_CHECK_S = 1.0             # auditor runs this often; dashboard turns red well within 2 s of a tamper
METER_OFFLINE_S = 150            # no batch/heartbeat for this long -> meter offline (field mode sends every 60 s)

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

# Fair-play weights sr-1.0 (brief §7, PLAN_B B-T09)
STREAK_WEIGHTS = (1.0, 1.0, 0.5, 0.25)
COOLDOWN_H = 2                   # cooldown lasts >= 2 h after the 4th play ...
COOLDOWN_OTHER_SONGS = 3         # ... AND >= 3 other plays in the venue since then
RESET_MIN = 30                   # normal streak reset: >= 30 min since this song's last play ...
RESET_OTHER_SONGS = 3            # ... AND >= 3 other plays in between
LOOP_MIN_RUN = 4                 # >= 4 back-to-back plays of one song ...
LOOP_GAP_TOL_S = 20              # ... each starting song_length +- 20 s after the previous -> flag "loop"
AUDIENCE_PCTL = 20               # play quieter than the venue's 20th percentile window loudness ...
AUDIENCE_FACTOR = 0.5            # ... or outside the venue's active hours -> x0.5 "low_audience"
ACTIVE_HOUR_MIN_SHARE = 0.10     # active hour = local hour holding >= 10 % of the venue's plays
AUDIENCE_MIN_PLAYS = 50          # D-008: active-hours test only once a venue has this many plays in the period
AUDIENCE_MIN_WINDOWS = 60        # D-008: loudness test only once a venue has this many received windows (10 min)
CONC_MIN_VENUES = 5              # song heard in < 5 venues ...
CONC_TOP2_SHARE = 0.60           # ... with top 2 venues > 60 % of its weighted plays -> cap + flag "concentration"
CONC_CAP_MULT = 3                # cap per venue = max(CONC_CAP_MIN, 3 x median per-(song,venue) weighted plays)
CONC_CAP_MIN = 5
# D-009: audience + concentration only FLAG plays for SONACAM review (the machine flags, a human decides).
# True = brief §7.2 original behaviour (x0.5 / cap applied to the weights automatically).
MODIFIERS_ADJUST_WEIGHTS = False

# Estimation + stats runs (brief §7.3 as amended by D-011: a meter in every bar, no scaling, no unidentified)
DEFAULT_CATCH_RATE = 0.8         # until the meter is calibrated (B-T14)
STATS_EVERY_S = 300              # scheduler: live period, both modes, every 5 min (only if plays changed)
STATS_AUTO_PERIODS = ("live",)   # mock_month / all: run after the mock import (B-T11) or POST /api/v1/stats/run
STATS_KEEP_RUNS = 3              # older runs (and their play_weights/shares) are pruned per (period, mode)

# Meter health (B-T14): calibration, clock skew, moved meter
CALIB_TOL_S = 60                 # contract §4: an expected play is caught if matched within ±60 s of played_at
CALIB_RECHECK_S = 600            # runs received in the last 10 min are re-evaluated (matching lags a little)
CALIB_EVERY_S = 15               # scheduler re-check interval
CLOCK_SKEW_MAX_S = 5.0           # brief §12: |meter clock − server clock| > 5 s → clock_skew flag
CLOCK_SKEW_EVERY_S = 3600        # at most one clock_skew flag per meter per hour

# The team's song package v3 (FP-001…FP-183) as imported: S-000013…S-000195 (song_map.csv in the package).
CATALOGUE_RANGE = ("S-000013", "S-000195")
CATALOGUE_SIZE = 183
