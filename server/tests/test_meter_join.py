"""New meters ask to join (signed with their own key) and wait for SONACAM's approval (server/joins.py)."""
import pytest
from fastapi.testclient import TestClient

from fairplay_core.signing import generate_seed, make_pub_record, sign_dict
from server import config
from server.db import connect

TOKEN = "test-admin-token"
H = {"X-Admin-Token": TOKEN}


@pytest.fixture
def cl(migrated_db, monkeypatch):
    monkeypatch.setattr(config, "DATABASE_URL", migrated_db)
    monkeypatch.setattr(config, "ADMIN_TOKEN", TOKEN)
    from server.api.main import app
    with TestClient(app) as c:
        with connect(migrated_db, autocommit=True) as db:
            db.execute("DELETE FROM meter_requests")
            db.execute("DELETE FROM meters WHERE meter_id IN ('M-81', 'M-82', 'M-83')")
        yield c


def join_body(meter, seed=None, computer="BAR-LAPTOP"):
    seed = seed or generate_seed()
    body = {**make_pub_record(meter, "V-BUEA-CIMFEST", seed), "computer": computer}
    body["sig"] = sign_dict(seed, body)
    return body, seed


def test_join_waits_for_approval_then_registers(cl, migrated_db):
    body, _ = join_body("M-81")
    r = cl.post("/v1/meters/join", json=body)
    assert r.status_code == 202 and r.json()["status"] == "pending"
    fp = r.json()["key_fingerprint"]
    assert cl.post("/v1/meters/join", json=body).json()["status"] == "pending"          # asking again: still waiting
    assert cl.get("/api/v1/admin/meter-requests").status_code == 403                    # SONACAM only
    waiting = cl.get("/api/v1/admin/meter-requests", headers=H).json()
    assert [(w["meter_id"], w["key_fingerprint"], w["computer"]) for w in waiting] == [("M-81", fp, "BAR-LAPTOP")]
    with connect(migrated_db) as db:                                                     # not a meter yet
        assert db.execute("SELECT 1 FROM meters WHERE meter_id = 'M-81'").fetchone() is None
    assert cl.post("/api/v1/admin/meter-requests/M-81/approve").status_code == 403
    a = cl.post("/api/v1/admin/meter-requests/M-81/approve", headers=H)
    assert a.status_code == 200 and a.json()["status"] == "approved"
    r = cl.post("/v1/meters/join", json=body)
    assert r.status_code == 200 and r.json()["status"] == "approved"
    with connect(migrated_db) as db:
        m = db.execute("SELECT source, retired_at FROM meters WHERE meter_id = 'M-81'").fetchone()
        assert m["source"] == "live" and m["retired_at"] is None
        log = [x["message"] for x in db.execute("SELECT message FROM activity_log WHERE meter_id = 'M-81' ORDER BY id")]
    assert any("asks to join" in x for x in log) and any("approved" in x for x in log)
    assert cl.get("/api/v1/admin/meter-requests", headers=H).json() == []
    assert cl.post("/api/v1/admin/meter-requests/M-81/approve", headers=H).status_code == 404   # nothing waiting


def test_reject_and_id_hijack_and_bad_signature(cl):
    body, _ = join_body("M-82")
    assert cl.post("/v1/meters/join", json=body).status_code == 202
    other, _ = join_body("M-82")                                                         # another key, same id
    assert cl.post("/v1/meters/join", json=other).json()["error"] == "meter_id_taken"
    forged = {**body, "public_key_b64": other["public_key_b64"]}                          # someone else's key, not signed by it
    assert cl.post("/v1/meters/join", json=forged).json()["error"] == "bad_signature"
    assert cl.post("/api/v1/admin/meter-requests/M-82/reject", headers=H).json()["status"] == "rejected"
    r = cl.post("/v1/meters/join", json=body)
    assert (r.status_code, r.json()["status"]) == (403, "rejected")
    assert cl.post("/v1/meters/join", json=other).status_code == 202                      # a rejected id can be asked for anew


def test_registered_id_cannot_be_taken(cl):
    body, _ = join_body("M-83")
    cl.post("/v1/meters/join", json=body)
    cl.post("/api/v1/admin/meter-requests/M-83/approve", headers=H)
    other, _ = join_body("M-83")
    r = cl.post("/v1/meters/join", json=other)
    assert (r.status_code, r.json()["error"]) == (409, "meter_id_taken")
    assert cl.post("/v1/meters/join", json={"meter_id": "nope"}).status_code == 422
