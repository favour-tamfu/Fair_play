"""Sign-in limits: password guessing over the internet is slowed down and then stopped for a while.

Failed sign-ins are counted in a 15-minute window (table login_failures):
  per account           5 failures  -> that account is locked for the rest of the window (per account AND address
                        when the address is known, so a stranger cannot lock SONACAM out)
  per internet address  20 failures -> that address cannot sign in for the rest of the window
                        (only when the proxy tells us the real address: X-Forwarded-For; otherwise every visitor would
                        share one address and one attacker could lock everybody out)
  all artist accounts   30 failures -> artist sign-in pauses for the rest of the window (stops trying one password
                        against every artist name); SONACAM's own account is never paused by this rule
A locked attempt is refused BEFORE the password is checked, so a locked account cannot be guessed. Every failure also
waits half a second. A successful sign-in clears that account's failures. Lockouts go to the activity log once.
"""
from __future__ import annotations

import ipaddress
import math
import time
from typing import Optional

import psycopg

WINDOW_S = 15 * 60
MAX_PER_ACCOUNT = 5
MAX_PER_ADDRESS = 20
MAX_ARTISTS_TOTAL = 30
FAIL_DELAY_S = 0.5


def client_address(headers, peer: Optional[str]) -> Optional[str]:
    """The visitor's address from X-Forwarded-For (first entry, set by the HTTPS proxy), or None if unknown."""
    fwd = (headers.get("x-forwarded-for") or "").split(",")[0].strip()
    try:
        return str(ipaddress.ip_address(fwd)) if fwd else None
    except ValueError:
        return None


def _keys(username: str, address: Optional[str]) -> dict[str, str]:
    u = (username or "").strip().lower()[:80]
    # per account AND address when the address is known: a stranger's wrong tries lock only the stranger, so nobody
    # can lock SONACAM out of its own account from elsewhere
    keys = {"account": f"user:{u}" + (f"|{address}" if address else "")}
    if address:
        keys["address"] = f"ip:{address}"
    if u != "sonacam":
        keys["artists"] = "artists:all"
    return keys


LIMITS = {"account": MAX_PER_ACCOUNT, "address": MAX_PER_ADDRESS, "artists": MAX_ARTISTS_TOTAL}


def blocked(conn: psycopg.Connection, username: str, address: Optional[str]) -> Optional[dict]:
    """None if this sign-in may be tried; else {"rule", "retry_after_s"}."""
    for rule, key in _keys(username, address).items():
        r = conn.execute(f"""SELECT count(*) AS n, min(at) AS first FROM login_failures
                             WHERE key = %s AND at > now() - interval '{WINDOW_S} seconds'""", (key,)).fetchone()
        if r["n"] >= LIMITS[rule]:
            left = WINDOW_S - (time.time() - r["first"].timestamp())
            return {"rule": rule, "retry_after_s": max(60, int(math.ceil(left)))}
    return None


def failed(conn: psycopg.Connection, username: str, address: Optional[str]) -> Optional[str]:
    """Count a failure; returns a lockout message the first time a limit is reached (for the activity log)."""
    keys = _keys(username, address)
    for key in keys.values():
        conn.execute("INSERT INTO login_failures (key) VALUES (%s)", (key,))
    conn.execute(f"DELETE FROM login_failures WHERE at < now() - interval '{2 * WINDOW_S} seconds'")
    msg = None
    for rule, key in keys.items():
        n = conn.execute(f"""SELECT count(*) AS n FROM login_failures
                             WHERE key = %s AND at > now() - interval '{WINDOW_S} seconds'""", (key,)).fetchone()["n"]
        if n == LIMITS[rule]:
            who = {"account": f"account “{username.strip()[:60]}”", "address": f"address {address}",
                   "artists": "all artist accounts"}[rule]
            msg = f"Sign-in locked for 15 min for {who} after {n} failed tries"
    return msg


def succeeded(conn: psycopg.Connection, username: str, address: Optional[str] = None) -> None:
    conn.execute("DELETE FROM login_failures WHERE key = %s", (_keys(username, address)["account"],))


def slow_down() -> None:
    time.sleep(FAIL_DELAY_S)
