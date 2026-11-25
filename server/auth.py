"""Role-based access (D-028).

Roles
  sonacam  SONACAM staff and admins (one role): the SONACAM app (dashboard, meters, catalogue, flags, activity log,
           actions) and every SONACAM-only API. Account 'sonacam', password = ADMIN_TOKEN from .env.
  artist   an artist (or their label): upload songs with metadata and see their own songs only (status, plays,
           share), never other artists or bars. Prototype accounts (Person B): user name = the artist's name as in
           the catalogue, password = ARTIST_DEFAULT_PASSWORD ("SONACAM"). Artists are verified on SONACAM's own site,
           so the account is created on first sign-in for any artist that has songs in the catalogue.
Sessions: a random token in an HttpOnly, SameSite=Lax cookie; only its SHA-256 is stored; 12 hours.
Scripts and tests can still send the header X-Admin-Token (= ADMIN_TOKEN) instead of a session.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import psycopg

from server import config

COOKIE = "fp_session"
SESSION_HOURS = 12


def hash_password(password: str, salt: Optional[bytes] = None) -> str:
    salt = salt or secrets.token_bytes(16)
    h = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${h.hex()}"


def check_password(password: str, stored: str) -> bool:
    try:
        kind, salt, h = stored.split("$")
    except ValueError:
        return False
    return kind == "scrypt" and hmac.compare_digest(hash_password(password, bytes.fromhex(salt)), stored)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def ensure_sonacam_user(conn: psycopg.Connection) -> None:
    """The SONACAM account follows ADMIN_TOKEN (.env): created, or its password updated when the token changed."""
    if not config.ADMIN_TOKEN:
        return
    row = conn.execute("SELECT password_hash FROM users WHERE username = 'sonacam'").fetchone()
    if row and check_password(config.ADMIN_TOKEN, row["password_hash"]):
        return
    conn.execute("""INSERT INTO users (username, display_name, role, password_hash) VALUES ('sonacam', 'SONACAM', 'sonacam', %s)
                    ON CONFLICT (username) DO UPDATE SET password_hash = EXCLUDED.password_hash, role = 'sonacam'""",
                 (hash_password(config.ADMIN_TOKEN),))


def login(conn: psycopg.Connection, username: str, password: str) -> Optional[dict[str, Any]]:
    """Check the password and open a session: returns {token, user} or None."""
    name = (username or "").strip()
    key = name.lower()
    if not key or not password:
        return None
    with conn.transaction():
        if key == "sonacam":
            ensure_sonacam_user(conn)
        user = conn.execute("SELECT * FROM users WHERE username = %s", (key,)).fetchone()
        if user is None:
            # first sign-in of an artist that has songs in the catalogue (prototype rule, Person B)
            art = conn.execute("""SELECT artist_name FROM songs WHERE lower(artist_name) = %s AND source = 'upload'
                                  ORDER BY song_id LIMIT 1""", (key,)).fetchone()
            if art is None or password != config.ARTIST_DEFAULT_PASSWORD:
                return None
            user = conn.execute("""INSERT INTO users (username, display_name, role, artist_name, password_hash)
                                   VALUES (%s, %s, 'artist', %s, %s) RETURNING *""",
                                (key, art["artist_name"], art["artist_name"], hash_password(password))).fetchone()
        elif not check_password(password, user["password_hash"]):
            return None
        token = secrets.token_urlsafe(32)
        conn.execute("INSERT INTO sessions (token_hash, username, expires_at) VALUES (%s, %s, %s)",
                     (_token_hash(token), user["username"], datetime.now(timezone.utc) + timedelta(hours=SESSION_HOURS)))
        conn.execute("UPDATE users SET last_login = now() WHERE username = %s", (user["username"],))
        conn.execute("DELETE FROM sessions WHERE expires_at < now()")
    return {"token": token, "user": public(user)}


def public(user: dict) -> dict:
    return {"username": user["username"], "name": user["display_name"], "role": user["role"],
            "artist_name": user.get("artist_name"),
            "home": "sonacam-x7k2q9.html" if user["role"] == "sonacam" else "portal.html"}


def session_user(conn: psycopg.Connection, token: Optional[str]) -> Optional[dict]:
    if not token:
        return None
    u = conn.execute("""SELECT u.* FROM sessions s JOIN users u USING (username)
                        WHERE s.token_hash = %s AND s.expires_at > now()""", (_token_hash(token),)).fetchone()
    return public(u) if u else None


def logout(conn: psycopg.Connection, token: Optional[str]) -> None:
    if token:
        conn.execute("DELETE FROM sessions WHERE token_hash = %s", (_token_hash(token),))
