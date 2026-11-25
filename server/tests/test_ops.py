"""D-029: SONACAM retires a meter (its reports are refused until re-registered) and marks review flags reviewed."""
from datetime import datetime, timedelta, timezone

from server.db import connect
from server.tests.test_ingest import SEED, T0, clean, client, hb, make, q  # noqa: F401  (fixtures: M-90 registered)


def test_meter_list_has_key_fingerprint(client):
    ms = {m["meter_id"]: m for m in client.get("/api/v1/admin/meters").json()}
    m = ms["M-90"]
    assert len(m["key_fingerprint"].replace(" ", "")) == 16 and m["retired_at"] is None
    assert all(x["source"] != "mock" for x in ms.values())


def test_retire_refuses_reports_until_re_registered(client, migrated_db):
    assert client.post("/v1/batches", json=make(501, seconds=5010)).status_code == 200
    r = client.post("/api/v1/admin/meters/M-90/retire")
    assert r.status_code == 200 and r.json()["changed"] is True
    assert client.post("/api/v1/admin/meters/M-90/retire").json()["changed"] is False          # already retired
    b = client.post("/v1/batches", json=make(502, seconds=5020))
    assert (b.status_code, b.json()["error"]) == (403, "meter_retired")
    assert client.post("/v1/heartbeat", json=hb(datetime.now(timezone.utc))).status_code == 403
    lines = [r["message"] for r in q(migrated_db, "SELECT message FROM activity_log ORDER BY id DESC LIMIT 5")]
    assert any("retired" in m for m in lines)
    key = q(migrated_db, "SELECT public_key_b64, venue_id FROM meters WHERE meter_id = 'M-90'")[0]
    rec = {"meter_id": "M-90", "venue_id": key["venue_id"], "public_key_b64": key["public_key_b64"],
           "created_at": "2026-11-24T00:00:00.000Z"}
    assert client.post("/v1/meters/register", json=rec).status_code == 200                   # open mode in tests = admin
    assert client.post("/v1/batches", json=make(503, seconds=5030)).status_code == 200
    assert client.post("/api/v1/admin/meters/NOPE/retire").status_code == 404


def test_review_a_flag(client, migrated_db):
    with connect(migrated_db, autocommit=True) as c:
        fid = c.execute("""INSERT INTO flags (type, venue_id, detail, created_at) VALUES ('clock_skew', 'V-BUEA-CIMFEST', 'x', %s)
                           RETURNING flag_id""", (datetime.now(timezone.utc) + timedelta(seconds=1),)).fetchone()["flag_id"]
    assert client.post(f"/api/v1/flags/{fid}/review", json={"reviewed": True, "note": "meter restarted"}).status_code == 200
    f = next(x for x in client.get("/api/v1/flags", params={"period": "live"}).json() if x["flag_id"] == fid)
    assert f["reviewed_at"] and f["reviewed_by"]
    assert client.post(f"/api/v1/flags/{fid}/review", json={"reviewed": False}).status_code == 200
    f = next(x for x in client.get("/api/v1/flags", params={"period": "live"}).json() if x["flag_id"] == fid)
    assert f["reviewed_at"] is None
    assert client.post("/api/v1/flags/999999/review", json={}).status_code == 404
