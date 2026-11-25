"""Shared fixtures for server tests.

DB tests run against a separate database `<db>_test` (created fresh per test session) so they never touch demo data.
If Postgres is not reachable (stack not running) those tests are skipped, not failed.
"""
from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest

from server import config


def _with_db(url: str, dbname: str) -> str:
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc, "/" + dbname, p.query, p.fragment))


@pytest.fixture(scope="session")
def test_db_url():
    base = config.DATABASE_URL
    name = urlsplit(base).path.lstrip("/") + "_test"
    try:
        admin = psycopg.connect(_with_db(base, "postgres"), autocommit=True, connect_timeout=3)
    except psycopg.OperationalError:
        pytest.skip("Postgres not reachable — start the stack: docker compose up -d")
    with admin:
        admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        admin.execute(f'CREATE DATABASE "{name}"')
    return _with_db(base, name)


@pytest.fixture(scope="session")
def migrated_db(test_db_url):
    from server.db.migrate import migrate
    migrate(test_db_url)
    return test_db_url


@pytest.fixture(scope="session", autouse=True)
def _no_admin_token():
    """Tests run with admin actions open (also module-scoped fixtures); test_admin.py sets a token itself (D-020)."""
    mp = pytest.MonkeyPatch()
    mp.setattr(config, "ADMIN_TOKEN", "")
    yield
    mp.undo()
