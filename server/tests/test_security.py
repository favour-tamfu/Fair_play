"""Security measures: sign-in limits, bars hidden from the public, browser protections, meter request size cap,
refusal flood guard."""
import pytest
from fastapi.testclient import TestClient

from server import config
from server.db import connect

TOKEN = "test-admin-token"
H = {"X-Admin-Token": TOKEN}


@pytest.fixture
def cl(migrated_db, monkeypatch):
    monkeypatch.setattr(config, "DATABASE_URL", migrated_db)
    monkeypatch.setattr(config, "ADMIN_TOKEN", TOKEN)
    from server import login_guard
    monkeypatch.setattr(login_guard, "FAIL_DELAY_S", 0)
    from server.api.main import app
    with TestClient(app) as c:
        with connect(migrated_db, autocommit=True) as db:
            db.execute("DELETE FROM login_failures")
        yield c


def login(cl, user, pw, ip=None):
    return cl.post("/api/v1/auth/login", json={"username": user, "password": pw},
                   headers={"X-Forwarded-For": ip} if ip else {})


def test_account_locks_after_five_failures_even_for_the_right_password(cl):
    for _ in range(5):
        assert login(cl, "sonacam", "wrong").status_code == 401
    r = login(cl, "sonacam", TOKEN)
    assert r.status_code == 429 and int(r.headers["Retry-After"]) >= 60
    assert "Try again in" in r.json()["detail"]


def test_a_stranger_cannot_lock_sonacam_out(cl):
    for _ in range(5):
        login(cl, "sonacam", "wrong", ip="203.0.113.50")
    assert login(cl, "sonacam", TOKEN, ip="203.0.113.50").status_code == 429     # the stranger is locked
    assert login(cl, "sonacam", TOKEN, ip="198.51.100.20").status_code == 200    # SONACAM elsewhere is not


def test_success_clears_the_account_count(cl):
    for _ in range(4):
        login(cl, "sonacam", "wrong")
    assert login(cl, "sonacam", TOKEN).status_code == 200
    for _ in range(4):
        login(cl, "sonacam", "wrong")
    assert login(cl, "sonacam", TOKEN).status_code == 200                 # 4 + 4: never 5 in a row


def test_one_address_is_stopped_across_accounts(cl):
    for i in range(20):
        login(cl, f"someone{i}", "wrong", ip="203.0.113.7")
    assert login(cl, "sonacam", TOKEN, ip="203.0.113.7").status_code == 429
    assert login(cl, "sonacam", TOKEN, ip="198.51.100.9").status_code == 200   # other visitors are not affected


def test_guessing_one_password_on_every_artist_pauses_artists_not_sonacam(cl):
    for i in range(30):
        login(cl, f"artist{i}", "SONACAM")
    assert login(cl, "anyartist", "SONACAM").status_code == 429
    assert login(cl, "sonacam", TOKEN).status_code == 200                  # SONACAM can still sign in


def test_bars_are_city_level_for_the_public(cl):
    public = cl.get("/api/v1/venues").json()
    full = cl.get("/api/v1/venues", headers=H).json()
    assert public and len(public) == len(full)
    real_ids = {v["venue_id"] for v in full}
    real_names = {v["name"] for v in full if v["name"] and not v["name"].startswith("A bar")}
    for v in public:
        assert v["venue_id"] not in real_ids and v["venue_id"].startswith("B-")
        assert v["name"] not in real_names and v["name"].startswith("A bar")
        assert set(v) <= {"venue_id", "name", "city", "lat", "lon", "source", "demo", "plays", "meters"}
        assert all(set(m) == {"online"} for m in v["meters"])
        for k in ("lat", "lon"):
            assert v[k] is None or round(v[k], 1) == v[k]
    assert sum(v["demo"] for v in public) <= 1


def test_browser_protections_on_every_answer(cl):
    r = cl.get("/health", headers={"X-Forwarded-Proto": "https"})
    assert r.headers["X-Frame-Options"] == "DENY" and r.headers["X-Content-Type-Options"] == "nosniff"
    assert "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]
    assert "Strict-Transport-Security" in r.headers
    assert cl.get("/api/v1/overview").headers["Cache-Control"] == "no-store"


def test_secure_cookie_behind_the_https_proxy(cl):
    r = cl.post("/api/v1/auth/login", json={"username": "sonacam", "password": TOKEN}, headers={"X-Forwarded-Proto": "https"})
    assert r.status_code == 200 and "secure" in r.headers["set-cookie"].lower()


def test_oversized_meter_request_is_refused(cl):
    r = cl.post("/v1/batches", content=b"x" * (4 * 1024 * 1024 + 1), headers={"Content-Type": "application/json"})
    assert r.status_code == 413


def test_repeated_refusals_are_logged_once_a_minute(cl, migrated_db):
    bad = {"meter_id": "M-58", "venue_id": "V-X", "seq": 1, "window_start": "2026-11-24T21:00:00.000Z",
           "window_s": 10, "peaks": [], "loudness_db": -20.0, "sig": "x"}
    for seq in (1, 2, 3):
        assert cl.post("/v1/batches", json={**bad, "seq": seq}).status_code >= 400
    with connect(migrated_db) as db:
        n = db.execute("SELECT count(*) AS n FROM activity_log WHERE kind = 'rejected' AND meter_id = 'M-58'").fetchone()["n"]
    assert n == 1
