"""D-024: activity log for admins — events recorded, refused requests and admin actions recorded, admin-only API."""
import pytest
from fastapi.testclient import TestClient

from server import activity, config
from server.db import connect, notify

TOKEN = "test-admin-token"
H = {"X-Admin-Token": TOKEN}


@pytest.fixture
def cl(migrated_db, monkeypatch):
    monkeypatch.setattr(config, "DATABASE_URL", migrated_db)
    monkeypatch.setattr(config, "ADMIN_TOKEN", TOKEN)
    with connect(migrated_db, autocommit=True) as c:
        c.execute("TRUNCATE activity_log")
    from server.api.main import app
    with TestClient(app) as c:
        yield c


def rows(cl, **params):
    r = cl.get("/api/v1/admin/activity", params=params, headers=H)
    assert r.status_code == 200
    return r.json()["rows"]


def test_events_are_recorded_and_filtered(cl, migrated_db):
    with connect(migrated_db, autocommit=True) as c:
        notify(c, "batch", {"meter_id": "M-07", "venue_id": "V-BUEA-CIMFEST", "seq": 12, "late": False})
        notify(c, "match", {"meter_id": "M-07", "venue_id": "V-BUEA-CIMFEST", "song_id": "S-000042", "title": "Partout",
                            "accepted": True})
        notify(c, "match", {"meter_id": "M-07", "accepted": False})                       # no match: not recorded
        notify(c, "meter", {"meter_id": "M-07", "online": True})                         # every report: not recorded
        notify(c, "ledger", {"intact": False, "broken_at_play_id": "P-1"})
        activity.record(c, "meter", "M-11 is offline", "warn", meter_id="M-11")
    all_rows = rows(cl)
    assert [r["kind"] for r in all_rows] == ["meter", "ledger", "heard", "report"]           # newest first
    assert all_rows[2]["message"] == "M-07 heard “Partout” (S-000042)"
    assert [r["kind"] for r in rows(cl, level="warn")] == ["meter", "ledger"]               # warnings and errors
    assert [r["kind"] for r in rows(cl, kind="report,heard")] == ["heard", "report"]
    assert [r["meter_id"] for r in rows(cl, meter_id="M-11")] == ["M-11"]
    assert [r["kind"] for r in rows(cl, q="partout")] == ["heard"]
    newest = all_rows[0]["id"]
    assert rows(cl, after_id=newest) == []                                                   # live polling: nothing new
    csv = cl.get("/api/v1/admin/activity.csv", headers=H)
    assert csv.status_code == 200 and csv.text.splitlines()[0].startswith("id,time_utc,kind") and len(csv.text.splitlines()) == 5


def test_admin_only(cl):
    assert cl.get("/api/v1/admin/activity").status_code == 403
    assert cl.get("/api/v1/admin/activity.csv", headers={"X-Admin-Token": "wrong"}).status_code == 403


def test_refused_device_request_and_admin_actions_are_recorded(cl):
    r = cl.post("/v1/batches", json={"meter_id": "M-55", "venue_id": "V-X", "seq": 3, "window_start": "2026-11-24T21:00:00.000Z",
                                      "window_s": 10, "peaks": [], "loudness_db": -20.0, "sig": "x"})
    assert r.status_code >= 400
    assert cl.post("/api/v1/stats/run?period=live").status_code == 403                     # no password
    assert cl.post("/api/v1/stats/run?period=live", headers=H).status_code == 200
    got = {(r["kind"], r["level"]): r["message"] for r in rows(cl, kind="rejected,admin")}
    assert "Refused report #3 from M-55" in got[("rejected", "warn")] or "Refused report #3 from M-55" in got.get(("rejected", "error"), "")
    assert got[("admin", "warn")] == "Refused: an attempt to recompute the shares without the right admin password"
    assert got[("admin", "info")] == "Admin recomputed the shares (period: live)"
