"""New meters ask to join; SONACAM approves or rejects them (no key files to copy, no token on the bar's laptop).

A meter that has just made its key sends POST /v1/meters/join with its .pub.json record, an optional computer name and
`sig`: the record signed with its own private key (so nobody can file a request for a key they do not hold). The meter
re-sends the same request to ask how it stands. Answers (`status`):
  pending   SONACAM has not decided yet (202)
  approved  the meter is registered: its reports are accepted (200)
  rejected  SONACAM said no (403)
  retired   the meter was registered and later retired (403)
Errors: 401 bad_signature, 409 meter_id_taken (another key holds or waits for this id), 422 invalid, 429 too_many_requests.
One computer, one meter (optional signed `device_id`, a hash of the computer's machine id): 409 device_already_waiting
when the same computer already waits under another id (a request not re-asked for 10 min is replaced instead), and
409 device_has_meter when the computer already is an active meter (SONACAM retires it first).
Until approval the meter is unknown, so its reports are refused with 404 and wait in its outbox: a smuggled meter
cannot add plays until SONACAM has looked at it.
"""
from __future__ import annotations

from typing import Any, Optional

import psycopg

from fairplay_core.signing import validate_pub_record, verify_dict
from server import activity, ingest
from server.registry import PUB_FIELDS, key_fingerprint, upsert_meter

MAX_PENDING = 50
STALE_S = 600          # a waiting request not re-asked for 10 min may be replaced by another from the same computer


def _status(code: int, status: str, meter_id: str, key: str, **extra: Any) -> ingest.Result:
    return ingest.Result(code, {"status": status, "meter_id": meter_id, "key_fingerprint": key_fingerprint(key), **extra})


def request_join(conn: psycopg.Connection, body: Any) -> ingest.Result:
    if not isinstance(body, dict):
        return ingest.Result(422, {"error": "invalid", "detail": "body must be a .pub.json object with sig"})
    try:
        rec = validate_pub_record({k: body[k] for k in PUB_FIELDS if k in body})
    except (ValueError, KeyError, TypeError) as e:
        return ingest.Result(422, {"error": "invalid", "detail": str(e)})
    if not verify_dict(rec["public_key_b64"], {k: v for k, v in body.items()}):
        return ingest.Result(401, {"error": "bad_signature", "detail": "the request must be signed with the meter's own key"})
    mid, key = rec["meter_id"], rec["public_key_b64"]
    computer = str(body.get("computer") or "")[:80] or None
    device = str(body.get("device_id") or "")[:64] or None
    taken = {"error": "meter_id_taken", "detail": f"{mid} belongs to another meter: choose another meter id"}

    with conn.transaction():
        m = conn.execute("SELECT public_key_b64, retired_at FROM meters WHERE meter_id = %s", (mid,)).fetchone()
        if m is not None:
            if m["public_key_b64"] != key:
                return ingest.Result(409, taken)
            if m["retired_at"] is not None:
                return _status(403, "retired", mid, key)
            return _status(200, "approved", mid, key)
        if device:                                              # one meter per computer
            active = conn.execute("""SELECT r.meter_id FROM meter_requests r JOIN meters m USING (meter_id)
                                     WHERE r.device_id = %s AND r.status = 'approved' AND r.meter_id <> %s
                                       AND m.retired_at IS NULL LIMIT 1""", (device, mid)).fetchone()
            if active:
                return ingest.Result(409, {"error": "device_has_meter", "meter": active["meter_id"],
                                           "detail": f"this computer is already meter {active['meter_id']}; "
                                                     "SONACAM must retire it before this computer can ask again"})
        r = conn.execute("SELECT * FROM meter_requests WHERE meter_id = %s FOR UPDATE", (mid,)).fetchone()
        if r is not None and r["public_key_b64"] == key:
            conn.execute("UPDATE meter_requests SET last_asked_at = now() WHERE meter_id = %s", (mid,))
            if r["status"] == "rejected":
                return _status(403, "rejected", mid, key)
            return _status(202, "pending", mid, key)            # 'approved' rows always have a meters row (handled above)
        if r is not None and r["status"] == "pending":
            return ingest.Result(409, taken)                    # someone else's request waits for this id
        if device:                                              # one waiting request per computer
            other = conn.execute("""SELECT meter_id, last_asked_at > now() - %s * interval '1 second' AS live
                                    FROM meter_requests WHERE device_id = %s AND status = 'pending' AND meter_id <> %s""",
                                 (STALE_S, device, mid)).fetchall()
            alive = [o["meter_id"] for o in other if o["live"]]
            if alive:
                return ingest.Result(409, {"error": "device_already_waiting", "meter": alive[0],
                                           "detail": f"this computer already asked to join as {alive[0]}"})
            for o in other:                                     # left behind by a copy that stopped asking: replace it
                conn.execute("DELETE FROM meter_requests WHERE meter_id = %s", (o["meter_id"],))
                activity.record(conn, "meter", f"Waiting request {o['meter_id']} replaced by {mid} (same computer)",
                                meter_id=o["meter_id"])
        n = conn.execute("SELECT count(*) AS n FROM meter_requests WHERE status = 'pending'").fetchone()["n"]
        if n >= MAX_PENDING:
            return ingest.Result(429, {"error": "too_many_requests", "detail": "too many meters are waiting; try later"})
        conn.execute(
            """INSERT INTO meter_requests (meter_id, venue_id, public_key_b64, created_at, computer, device_id)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (meter_id) DO UPDATE SET venue_id = EXCLUDED.venue_id, public_key_b64 = EXCLUDED.public_key_b64,
                 created_at = EXCLUDED.created_at, computer = EXCLUDED.computer, device_id = EXCLUDED.device_id,
                 status = 'pending', requested_at = now(), last_asked_at = now(), decided_at = NULL, decided_by = NULL""",
            (mid, rec["venue_id"], key, rec.get("created_at"), computer, device))
        activity.record(conn, "meter", f"New meter {mid} at {rec['venue_id']} asks to join (key {key_fingerprint(key)}"
                        + (f", computer {computer}" if computer else "") + "): approve or reject it under Meters",
                        "warn", meter_id=mid, venue_id=rec["venue_id"])
    return _status(202, "pending", mid, key)


def pending(conn: psycopg.Connection) -> list[dict[str, Any]]:
    from fairplay_core.schema import format_utc
    rows = conn.execute("""SELECT r.*, v.name AS venue_name, v.city FROM meter_requests r LEFT JOIN venues v USING (venue_id)
                           WHERE r.status = 'pending' ORDER BY r.requested_at""").fetchall()
    return [{"meter_id": r["meter_id"], "venue_id": r["venue_id"], "bar": r["venue_name"] or r["venue_id"],
             "city": r["city"], "computer": r["computer"], "key_fingerprint": key_fingerprint(r["public_key_b64"]),
             "requested_at": format_utc(r["requested_at"]), "last_asked_at": format_utc(r["last_asked_at"])}
            for r in rows]


def decide(conn: psycopg.Connection, meter_id: str, approve: bool, who: str) -> Optional[dict[str, Any]]:
    """Approve (register the meter) or reject a pending request. None if there is no pending request for this id."""
    with conn.transaction():
        r = conn.execute("SELECT * FROM meter_requests WHERE meter_id = %s AND status = 'pending' FOR UPDATE",
                         (meter_id,)).fetchone()
        if r is None:
            return None
        if approve:
            upsert_meter(conn, {k: r[k] for k in PUB_FIELDS if r.get(k)})
            # a meter approved here is a real meter in a bar, whatever its number (registry.meter_source guesses by number)
            conn.execute("UPDATE meters SET source = 'live', retired_at = NULL WHERE meter_id = %s", (meter_id,))
        conn.execute("UPDATE meter_requests SET status = %s, decided_at = now(), decided_by = %s WHERE meter_id = %s",
                     ("approved" if approve else "rejected", who, meter_id))
        activity.record(conn, "meter", f"{meter_id} {'approved' if approve else 'rejected'} by {who}"
                        + ("" if approve else ": its reports stay refused"), "info" if approve else "warn",
                        meter_id=meter_id, venue_id=r["venue_id"], actor=who)
    return {"meter_id": meter_id, "status": "approved" if approve else "rejected"}
