"""Admin protection (audit fixes 1–2, D-020).

SONACAM-only actions need a signed-in SONACAM user (D-028) or the header `X-Admin-Token: <ADMIN_TOKEN from .env>`:
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

from fastapi import Header, HTTPException, Request

from server import config

HEADER = "X-Admin-Token"


def token_ok(token: Optional[str]) -> bool:
    if not config.ADMIN_TOKEN:
        return True
    return hmac.compare_digest((token or "").encode(), config.ADMIN_TOKEN.encode())


def current_user(request: Request) -> Optional[dict]:
    """The signed-in user (D-028) from the session cookie, or None."""
    from server import auth
    from server.db import connect
    token = request.cookies.get(auth.COOKIE)
    if not token:
        return None
    with connect() as c:
        return auth.session_user(c, token)


def is_sonacam(request: Request, x_admin_token: Optional[str]) -> bool:
    if not config.ADMIN_TOKEN:          # developer laptops and tests: open
        return True
    if x_admin_token and token_ok(x_admin_token):
        return True
    u = current_user(request)
    return bool(u and u["role"] == "sonacam")


def require_admin(request: Request, x_admin_token: Optional[str] = Header(None)) -> None:
    """FastAPI dependency for SONACAM-only routes: a signed-in SONACAM user, or the X-Admin-Token header."""
    if not is_sonacam(request, x_admin_token):
        raise HTTPException(403, detail="SONACAM only: sign in as SONACAM (or send the X-Admin-Token header)")


def require_uploader(request: Request, x_admin_token: Optional[str] = Header(None)) -> dict:
    """Song upload: SONACAM (any artist) or a signed-in artist (their own name only)."""
    if is_sonacam(request, x_admin_token):
        return {"role": "sonacam"}
    u = current_user(request)
    if u and u["role"] == "artist":
        return u
    raise HTTPException(403, detail="sign in to upload a song")


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
