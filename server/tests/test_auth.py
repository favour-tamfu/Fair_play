"""D-028: role-based access — SONACAM (one role) and artists (own songs only); public endpoints stay aggregated."""
import json

import pytest
from fastapi.testclient import TestClient

from server import config
from server.api.feed import _public
from server.auth import check_password, hash_password
from server.db import connect
from server.tests.test_songs import OWNERS, melody, write_wav

TOKEN = "test-admin-token"


@pytest.fixture
def app_client(migrated_db, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DATABASE_URL", migrated_db)
    monkeypatch.setattr(config, "ADMIN_TOKEN", TOKEN)
    monkeypatch.setattr(config, "SONGS_DIR", tmp_path / "songs")
    with connect(migrated_db, autocommit=True) as c:
        c.execute("TRUNCATE users, sessions CASCADE")
        c.execute("TRUNCATE songs, owners, fp_hashes, flags, jobs RESTART IDENTITY CASCADE")
        c.execute("ALTER SEQUENCE song_upload_seq RESTART WITH 10")
        c.execute("""INSERT INTO songs (song_id, title, artist_name, status, n_hashes, source) VALUES
                     ('S-000001', 'Ndutu', 'Locko', 'ready', 10, 'upload'), ('S-000002', 'Sango', 'Kocee', 'ready', 10, 'upload')""")
    from server.api.main import app
    return app


def sign_in(app, username, password):
    c = TestClient(app)
    c.__enter__()
    r = c.post("/api/v1/auth/login", json={"username": username, "password": password})
    return c, r


def test_password_hash():
    h = hash_password("SONACAM")
    assert check_password("SONACAM", h) and not check_password("sonacam", h) and h.startswith("scrypt$")


def test_anonymous_sees_aggregates_only(app_client):
    with TestClient(app_client) as c:
        for path in ("/api/v1/plays", "/api/v1/flags", "/api/v1/artists/Locko", "/api/v1/export/usage_report.csv",
                     "/api/v1/admin/activity", "/api/v1/me/songs"):
            assert c.get(path).status_code in (401, 403), path
        for path in ("/api/v1/overview", "/api/v1/artist-shares", "/api/v1/venues", "/api/v1/public/recent-plays"):
            assert c.get(path).status_code == 200, path
        assert c.get("/api/v1/auth/me").status_code == 401


def test_sonacam_signs_in_with_the_admin_password(app_client):
    c, r = sign_in(app_client, "SONACAM", TOKEN)
    assert r.status_code == 200 and r.json()["user"]["role"] == "sonacam" and r.json()["user"]["home"].startswith("sonacam-")
    assert c.get("/api/v1/plays").status_code == 200 and c.get("/api/v1/admin/activity").status_code == 200
    assert c.get("/api/v1/me/songs").status_code == 403                       # not an artist
    assert c.post("/api/v1/auth/logout").status_code == 200
    assert c.get("/api/v1/plays").status_code == 403                          # session closed
    assert sign_in(app_client, "sonacam", "wrong")[1].status_code == 401


def test_artist_sees_own_songs_only_and_uploads_under_own_name(app_client, tmp_path):
    c, r = sign_in(app_client, "locko", config.ARTIST_DEFAULT_PASSWORD)        # name is not case-sensitive
    assert r.status_code == 200 and r.json()["user"] == {"username": "locko", "name": "Locko", "role": "artist",
                                                         "artist_name": "Locko", "home": "portal.html"}
    mine = c.get("/api/v1/me/songs").json()
    assert mine["artist_name"] == "Locko" and [s["song_id"] for s in mine["songs"]] == ["S-000001"]
    assert set(mine["totals"]) == {"live", "mock_month"}
    for path in ("/api/v1/plays", "/api/v1/artists/Kocee", "/api/v1/artists/Locko", "/api/v1/admin/activity"):
        assert c.get(path).status_code == 403, path
    wav = write_wav(tmp_path / "x.wav", melody(5, seconds=12))
    with open(wav, "rb") as f:
        up = c.post("/api/v1/songs", files={"file": ("x.wav", f, "audio/wav")},
                    data={"title": "New one", "artist_name": "Kocee",                  # tries another artist's name
                          "owners": json.dumps([{"name": "Locko", "role": "singer", "share_pct": 100}]), "consent": "true"})
    assert up.status_code == 201, up.text
    with connect(config.DATABASE_URL) as db:
        assert db.execute("SELECT artist_name FROM songs WHERE song_id = %s", (up.json()["song_id"],)).fetchone()["artist_name"] == "Locko"
    assert sign_in(app_client, "Locko", "wrong")[1].status_code == 401
    assert sign_in(app_client, "Nobody", config.ARTIST_DEFAULT_PASSWORD)[1].status_code == 401   # not in the catalogue


def test_upload_needs_a_signed_in_uploader(app_client, tmp_path):
    wav = write_wav(tmp_path / "y.wav", melody(6, seconds=12))
    with TestClient(app_client) as c, open(wav, "rb") as f:
        r = c.post("/api/v1/songs", files={"file": ("y.wav", f, "audio/wav")},
                   data={"title": "Y", "artist_name": "Z", "owners": json.dumps(OWNERS), "consent": "true"})
        assert r.status_code == 403


def test_public_feed_hides_bars_and_detail():
    play = {"event": "play", "data": {"play_id": "P-1", "venue_id": "V-DLA-AKWA01", "meter_id": "M-1", "song_id": "S-1",
                                      "title": "T", "artist_name": "A", "city": "Douala", "started_at": "x", "source": "live"}}
    out = _public(play)["data"]
    assert out["city"] == "Douala" and "venue_id" not in out and "meter_id" not in out and "play_id" not in out
    assert _public({"event": "batch", "data": {"meter_id": "M-1"}}) is None
    assert _public({"event": "match", "data": {"accepted": True}}) is None
    assert _public({"event": "flag", "data": {}}) is None
    assert _public({"event": "play", "data": {**play["data"], "artist_name": "Fair Play test artist"}}) is None
