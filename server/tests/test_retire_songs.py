"""Audit fix #3: retire test songs; live plays force a demo reset (log stays intact); mock-month songs refused."""
import pytest

from server import config
from server.db import connect
from server.ledger import audit
from server.tests.test_demo_reset import world  # noqa: F401  (fixture: live play of S-000001, mock month, anchor)
from server.tests.test_import_mock import db  # noqa: F401
from server.tools.retire_songs import expand, retire


def test_expand():
    assert expand("S-000001..S-000003") == ["S-000001", "S-000002", "S-000003"] and expand("S-1, S-2") == ["S-1", "S-2"]


def test_retire(world, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.setattr(config, "SONGS_DIR", tmp_path / "songs")
    (tmp_path / "songs").mkdir()
    (tmp_path / "songs" / "S-000001.mp3").write_bytes(b"x")
    with connect(world, autocommit=True) as c:
        c.execute("INSERT INTO songs (song_id, title, artist_name, status, source, file_path) "
                  "VALUES ('S-000001','Test','T','ready','upload',%s), ('S-000002','Unused','T','ready','upload',NULL)",
                  (str(tmp_path / "songs" / "S-000001.mp3"),))
        c.execute("INSERT INTO owners (song_id, owner_name, role, share_pct) VALUES ('S-000001','T','singer',100)")
        with pytest.raises(SystemExit, match="mock-month plays"):
            retire(c, ["S-M0001"])                                     # used by the mock month: refused
        out = retire(c, ["S-000002"])
        assert out["live_plays"] == 0 and out["reset"] is None         # unused song: removed without a reset
        out = retire(c, ["S-000001"])                                  # the fixture has a live play of S-000001
        assert out["live_plays"] == 1 and out["reset"]["plays_removed"] >= 1 and out["files_removed"] == 1
        assert c.execute("SELECT count(*) AS n FROM songs WHERE song_id IN ('S-000001','S-000002')").fetchone()["n"] == 0
        assert c.execute("SELECT count(*) AS n FROM owners WHERE song_id = 'S-000001'").fetchone()["n"] == 0
        assert c.execute("SELECT count(*) AS n FROM plays WHERE chain = 'mock'").fetchone()["n"] == 4   # mock untouched
        audit._cache.clear()
        assert audit.status(c)["intact"]
    assert not (tmp_path / "songs" / "S-000001.mp3").exists()
