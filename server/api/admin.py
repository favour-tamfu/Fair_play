"""Admin protection (audit fixes 1–2, D-020).

Admin actions need the header `X-Admin-Token: <ADMIN_TOKEN from .env>`:
  POST /api/v1/demo/reset · POST /api/v1/stats/run · POST /api/v1/ledger/anchor · POST /api/v1/songs/{id}/approve
  POST /v1/meters/register when it would ADD an unknown meter or CHANGE a meter's public key.
Without a token, registration is only accepted when it changes nothing that matters: the meter already has exactly
this key, or the meter is new and its key is the one in contract/meters/<meter_id>.pub.json.
If ADMIN_TOKEN is empty (developer laptops, tests) the admin actions are open; demo_seed reports that as FAIL.
"""
from __future__ import annotations

import hmac
import json
from typing import Optional

from fastapi import Header, HTTPException

from server import config

HEADER = "X-Admin-Token"


def token_ok(token: Optional[str]) -> bool:
    if not config.ADMIN_TOKEN:
        return True
    return hmac.compare_digest((token or "").encode(), config.ADMIN_TOKEN.encode())


def require_admin(x_admin_token: Optional[str] = Header(None)) -> None:
    """FastAPI dependency for admin routes."""
    if not token_ok(x_admin_token):
        raise HTTPException(403, detail=f"admin action: send the admin token in the {HEADER} header")


def register_allowed_without_token(conn, rec: dict) -> bool:
    """Same key as stored, or a new meter whose key matches its file in contract/meters."""
    mid, key = rec.get("meter_id"), rec.get("public_key_b64")
    row = conn.execute("SELECT public_key_b64 FROM meters WHERE meter_id = %s", (mid,)).fetchone()
    if row is not None:
        return row["public_key_b64"] == key
    f = config.METERS_DIR / f"{mid}.pub.json"
    try:
        return f.is_file() and json.loads(f.read_text("utf-8")).get("public_key_b64") == key
    except (OSError, ValueError):
        return False
