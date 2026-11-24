"""Tests for the clock check (A-T08), offline parts."""
from device.tools.clockcheck import parse_server_time


def test_server_time_parses_to_epoch_seconds():
    assert parse_server_time("1970-01-01T00:00:01.500Z") == 1.5


def test_server_time_format_matches_the_contract():
    # contract: RFC 3339 UTC with milliseconds and Z, the same as /health returns
    value = parse_server_time("2026-11-24T05:23:58.434Z")
    assert 1.7e9 < value < 1.9e9  # a 2026 date in epoch seconds
