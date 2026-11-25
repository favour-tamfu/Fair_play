"""Audit fixes (D-020): admin token on admin actions; meter keys cannot be replaced without it; 503 when the DB is down."""
import json

import psycopg
import pytest
from fastapi.testclient import TestClient

from fairplay_core.signing import generate_seed, public_key_b64
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
        yield c


def rec(meter="M-07", key=None):
    return {"meter_id": meter, "venue_id": "V-BUEA-CIMFEST", "public_key_b64": key or public_key_b64(generate_seed()),
            "created_at": "2026-11-24T00:00:00.000Z"}


@pytest.mark.parametrize("path", ["/api/v1/demo/reset?confirm=yes", "/api/v1/stats/run?period=live",
                                  "/api/v1/ledger/anchor", "/api/v1/songs/S-000001/approve"])
def test_admin_actions_need_the_token(cl, path):
    assert cl.post(path).status_code == 403
    assert cl.post(path, headers={"X-Admin-Token": "wrong"}).status_code == 403
    assert cl.post(path, headers=H).status_code != 403


def test_meter_key_cannot_be_replaced_without_token(cl, migrated_db):
    m07 = json.loads((config.METERS_DIR / "M-07.pub.json").read_text("utf-8"))
    with connect(migrated_db, autocommit=True) as c:
        c.execute("DELETE FROM meters WHERE meter_id IN ('M-07', 'M-77')")
    good = {k: m07[k] for k in ("meter_id", "venue_id", "public_key_b64", "created_at")}
    assert cl.post("/v1/meters/register", json=good).status_code == 200          # new, key = contract/meters file
    assert cl.post("/v1/meters/register", json=good).status_code == 200          # same key again: fine
    attack = rec("M-07")
    r = cl.post("/v1/meters/register", json=attack)
    assert (r.status_code, r.json()["error"]) == (403, "admin_token_required")
    assert cl.post("/v1/meters/register", json=rec("M-77")).status_code == 403  # unknown new meter
    with connect(migrated_db) as c:
        assert c.execute("SELECT public_key_b64 FROM meters WHERE meter_id = 'M-07'").fetchone()["public_key_b64"] == \
            m07["public_key_b64"]
        assert c.execute("SELECT 1 FROM meters WHERE meter_id = 'M-77'").fetchone() is None
    r = cl.post("/v1/meters/register", json=attack, headers=H)                   # SONACAM admin may re-key a meter
    assert r.status_code == 200 and r.json()["changed_key"] is True
    assert cl.post("/v1/meters/register", json=good, headers=H).status_code == 200
    with connect(migrated_db, autocommit=True) as c:
        c.execute("DELETE FROM meters WHERE meter_id = 'M-77'")


def test_db_down_answers_503(cl, monkeypatch):
    from server.api import read

    def boom(*a, **k):
        raise psycopg.OperationalError("consuming input failed: terminating connection due to administrator command")
    monkeypatch.setattr(read, "_overview", boom)
    r = cl.get("/api/v1/overview")
    assert r.status_code == 503 and r.json()["error"] == "db_unavailable" and r.headers["retry-after"] == "2"


def test_artist_detail_is_sonacam_only(cl):
    """D-026: one artist's listening data (bars, days, recent plays) needs the admin password; the ranking stays public."""
    assert cl.get("/api/v1/artists/Locko").status_code == 403
    assert cl.get("/api/v1/artists/Locko", headers={"X-Admin-Token": "wrong"}).status_code == 403
    assert cl.get("/api/v1/artists/Locko", headers=H).status_code in (200, 404)
    assert cl.get("/api/v1/artists").status_code == 200                       # names and songs: public
    assert cl.get("/api/v1/artist-shares", params={"period": "live"}).status_code == 200   # the ranking: public
