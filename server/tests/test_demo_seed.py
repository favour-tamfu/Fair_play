"""B-T16: demo_seed reports what is missing instead of crashing (empty catalogue, api not reachable)."""
from server import config
from server.db import connect
from server.tools import demo_seed


def test_demo_seed_on_an_empty_catalogue(migrated_db, monkeypatch, capsys):
    monkeypatch.setattr(config, "DATABASE_URL", migrated_db)
    with connect(migrated_db, autocommit=True) as c:
        c.execute("TRUNCATE songs, owners, plays, play_weights, shares, stats_runs, flags CASCADE")
    rc = demo_seed.main(["--url", "http://127.0.0.1:9"])          # nothing listens on port 9
    out = capsys.readouterr().out
    assert rc == 1
    assert "FAIL  catalogue" in out and "0/0 songs ready" in out
    assert "FAIL  mock month" in out and "skipped: the catalogue is not ready" in out
    assert "OK    ledger" in out and "FAIL  api" in out and "FAIL  admin token" in out
