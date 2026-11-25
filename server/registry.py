"""Meter registry: which meters exist, where they hang, and their public keys (seal-checkers).

At api start-up every `contract/meters/*.pub.json` (written by Laptop A's provisioning tool) is loaded into the
`meters` table. A venue row is created if the venue is unknown (name = venue_id until the mock-month import or an
admin fills in city/coordinates). `POST /v1/meters/register` uses the same upsert.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Optional

import psycopg

from fairplay_core.signing import validate_pub_record
from server import config

log = logging.getLogger(__name__)
PUB_FIELDS = ("meter_id", "venue_id", "public_key_b64", "created_at")


def key_fingerprint(key_b64: Optional[str]) -> str:
    """Short, comparable fingerprint of a meter's public key: the meter prints the same one when it asks to join."""
    if not key_b64:
        return ""
    import hashlib
    h = hashlib.sha256(key_b64.encode()).hexdigest()[:16]
    return " ".join(h[i:i + 4] for i in range(0, 16, 4))


def meter_source(meter_id: str) -> str:
    """M-07 is the live meter (laptop mic); M-11 and above are virtual (WAV-fed) meters (PLAN_B B-T06)."""
    n = int(re.sub(r"\D", "", meter_id) or 0)
    return "virtual" if n >= 11 else "live"


def upsert_meter(conn: psycopg.Connection, rec: dict[str, Any]) -> dict[str, Any]:
    """Insert or update one meter from a .pub.json record. Returns {"meter_id", "changed_key": bool}."""
    rec = validate_pub_record({k: rec[k] for k in PUB_FIELDS if k in rec})
    conn.execute("INSERT INTO venues (venue_id, name, source) VALUES (%s, %s, 'live') ON CONFLICT (venue_id) DO NOTHING",
                 (rec["venue_id"], rec["venue_id"]))
    old = conn.execute("SELECT public_key_b64 FROM meters WHERE meter_id = %s", (rec["meter_id"],)).fetchone()
    conn.execute(
        """INSERT INTO meters (meter_id, venue_id, public_key_b64, source) VALUES (%s, %s, %s, %s)
           ON CONFLICT (meter_id) DO UPDATE SET venue_id = EXCLUDED.venue_id, public_key_b64 = EXCLUDED.public_key_b64""",
        (rec["meter_id"], rec["venue_id"], rec["public_key_b64"], meter_source(rec["meter_id"])))
    changed = bool(old and old["public_key_b64"] != rec["public_key_b64"])
    if changed:
        log.warning("meter %s: public key REPLACED", rec["meter_id"])
    return {"meter_id": rec["meter_id"], "changed_key": changed}


def load_meter_keys(conn: psycopg.Connection, meters_dir: Path = config.METERS_DIR) -> list[str]:
    """Load every *.pub.json in meters_dir. Bad files are logged and skipped (never block start-up)."""
    loaded = []
    for path in sorted(meters_dir.glob("*.pub.json")):
        try:
            loaded.append(upsert_meter(conn, json.loads(path.read_text(encoding="utf-8")))["meter_id"])
        except (ValueError, KeyError, json.JSONDecodeError) as e:
            log.error("skipping bad meter key file %s: %s", path.name, e)
    return loaded


def fill_known_venues(conn: psycopg.Connection) -> list[str]:
    """Fill EMPTY fields of venues we know in advance (config.KNOWN_VENUES, contract §7). Never overwrites."""
    done = []
    for vid, v in config.KNOWN_VENUES.items():
        conn.execute("INSERT INTO venues (venue_id, name, source) VALUES (%s, %s, 'live') ON CONFLICT DO NOTHING",
                     (vid, v["name"]))
        conn.execute("""UPDATE venues SET name = CASE WHEN name IS NULL OR name = venue_id THEN %s ELSE name END,
                        city = COALESCE(city, %s), lat = COALESCE(lat, %s), lon = COALESCE(lon, %s),
                        size_class = COALESCE(size_class, %s), stratum = COALESCE(stratum, %s) WHERE venue_id = %s""",
                     (v["name"], v["city"], v["lat"], v["lon"], v["size_class"], v["stratum"], vid))
        done.append(vid)
    return done


def get_meter(conn: psycopg.Connection, meter_id: str) -> Optional[dict[str, Any]]:
    return conn.execute("SELECT * FROM meters WHERE meter_id = %s", (meter_id,)).fetchone()
