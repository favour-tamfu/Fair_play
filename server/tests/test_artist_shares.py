"""B-T12 as decided (D-015): artists earn the sum of their songs' shares; frozen when the ledger is broken; mock
ownership; usage report (shares only)."""
import csv
import io
import json

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from server import config
from server.db import connect
from server.ledger import audit
from server.stats.artists import artist_shares
from server.stats.run import run_both
from server.tests.test_import_mock import db, write_month  # noqa: F401  (fixture + mini month)
from server.tools.artist_owners import set_artist_owners
from server.tools.import_mock import import_mock


@pytest.fixture
def month(db, tmp_path):                                                      # noqa: F811
    with connect(db, autocommit=True) as c:
        import_mock(c, write_month(tmp_path / "mm"))
        run_both(c, "mock_month")
        audit._cache.clear()
    return db


def test_artist_share_is_sum_of_their_songs(month):
    with connect(month, autocommit=True) as c:
        body = artist_shares(c, "mock_month")
        rid = body["stats_run_id"]
        sh = {r["song_id"]: r["share"] for r in c.execute("SELECT song_id, share FROM shares WHERE stats_run_id = %s", (rid,))}
    rows = {r["artist_name"]: r for r in body["rows"]}
    assert set(rows) == {"Mock Artist 01", "Mock Artist 02"} and not body["frozen"]
    assert rows["Mock Artist 01"]["share"] == pytest.approx(sh["S-M0001"] + sh["S-M0002"])
    assert rows["Mock Artist 01"]["n_songs"] == 2 and rows["Mock Artist 01"]["raw_plays"] == 3
    assert sum(r["share"] for r in body["rows"]) == pytest.approx(1.0)
    assert [r["rank"] for r in body["rows"]] == [1, 2] and body["rows"][0]["share"] >= body["rows"][1]["share"]
    assert body["rules"] and body["rule_version"] == "sr-1.0"


def test_api_schema_artist_page_and_usage_report(month):
    from server.api.main import app
    schema = json.loads((config.SCHEMAS_DIR / "artist_shares.schema.json").read_text("utf-8"))
    art_schema = json.loads((config.SCHEMAS_DIR / "artist.schema.json").read_text("utf-8"))
    with TestClient(app) as cl:
        body = cl.get("/api/v1/artist-shares", params={"period": "mock_month"}).json()
        assert list(Draft202012Validator(schema).iter_errors(body)) == []
        page = cl.get("/api/v1/artists/Mock Artist 01", params={"period": "mock_month"}).json()
        assert list(Draft202012Validator(art_schema).iter_errors(page)) == []
        assert page["share"] == pytest.approx(body["rows"][0 if body["rows"][0]["artist_name"] == "Mock Artist 01" else 1]["share"])
        r = cl.get("/api/v1/export/usage_report.csv", params={"period": "mock_month"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    lines = r.text.splitlines()
    assert lines[0].startswith("# Fair Play usage report (prototype)") and "WIPO" not in r.text
    rows = list(csv.DictReader(io.StringIO("\n".join(lines[1:]))))
    assert len(rows) == 3 and "amount_fcfa" not in rows[0]
    assert {x["song_id"] for x in rows} == {"S-M0001", "S-M0002", "S-M0003"}
    assert sum(float(x["share"]) for x in rows) == pytest.approx(1.0, abs=1e-5)


def test_frozen_when_ledger_broken(month):
    from server.api.main import app
    with connect(month, autocommit=True) as c:
        c.execute("UPDATE plays SET song_id = 'S-M0003' WHERE play_id = 'P-0000004'")     # tamper
        body = artist_shares(c, "mock_month")
    assert body["frozen"] and body["rows"] == []
    with TestClient(app) as cl:
        text = cl.get("/api/v1/export/usage_report.csv", params={"period": "mock_month"}).text
    assert "# FROZEN" in text and len(text.strip().splitlines()) == 3                # 2 comments + header only


def test_artist_owners_only_where_missing(db):                                   # noqa: F811
    with connect(db, autocommit=True) as c:
        for sid in ("S-000013", "S-000014", "S-000099"):
            c.execute("INSERT INTO songs (song_id, title, artist_name, status, source) VALUES (%s,'t','Locko','ready','upload')", (sid,))
        c.execute("INSERT INTO owners (song_id, owner_name, role, share_pct, momo) VALUES "
                  "('S-000014','Real Composer','composer',100,'+237699000001')")
        assert set_artist_owners(c, "S-000013", "S-000072") == ["S-000013"]      # S-000014 has owners, S-000099 out of range
        assert set_artist_owners(c, "S-000013", "S-000072") == []                # idempotent
        o = {r["song_id"]: (r["owner_name"], r["role"], r["share_pct"], r["momo"]) for r in c.execute("SELECT * FROM owners")}
    assert o == {"S-000013": ("Locko", "singer", 100, None), "S-000014": ("Real Composer", "composer", 100, "+237699000001")}
