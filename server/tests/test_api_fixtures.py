"""contract/fixtures/api: every file validates against its schema, is self-consistent, and is reproducible."""
import json

import pytest
from jsonschema import Draft202012Validator

from server import config
from server.tools.make_api_fixtures import OUT, POT, SCHEMA_OF, build

FEED_TYPES = {"batch", "match", "play", "flag", "ledger", "meter", "stats"}


def load(name):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", sorted(SCHEMA_OF))
def test_fixture_validates_against_schema(name):
    schema = json.loads((config.SCHEMAS_DIR / f"{SCHEMA_OF[name]}.schema.json").read_text(encoding="utf-8"))
    errors = [e.message for e in Draft202012Validator(schema).iter_errors(load(name))]
    assert errors == []


def test_committed_fixtures_equal_regenerated():
    for name, doc in build().items():
        committed = (OUT / name).read_text(encoding="utf-8")
        expected = doc if isinstance(doc, str) else json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
        assert committed == expected, f"{name} stale: run python -m server.tools.make_api_fixtures"


def test_money_adds_up():
    for name in ("shares_standardised.json", "shares_raw.json"):
        s = load(name)
        assert abs(sum(r["share"] for r in s["rows"]) - 1) < 1e-3
        assert sum(r["amount_fcfa"] for r in s["rows"]) == POT
        assert [r["share"] for r in s["rows"]] == sorted((r["share"] for r in s["rows"]), reverse=True)
    p = load("payouts.json")
    assert p["total_fcfa"] == sum(r["amount_fcfa"] for r in p["rows"]) == POT


def test_raw_vs_standardised_tell_the_loop_story():
    raw, std = load("shares_raw.json")["rows"], load("shares_standardised.json")["rows"]
    assert raw[0]["song_id"] == "S-M0015" and "loop" in raw[0]["flags"]          # looping song tops raw counts
    assert std[0]["song_id"] != "S-M0015"                                      # …but not after standardisation


def test_plays_newest_first_and_reference_known_venues():
    plays, venues = load("plays.json"), {v["venue_id"] for v in load("venues.json")}
    assert [p["started_at"] for p in plays] == sorted((p["started_at"] for p in plays), reverse=True)
    assert {p["venue_id"] for p in plays} <= venues
    assert "V-BUEA-CIMFEST" in venues


def test_feed_sample_is_valid_sse():
    blocks = [b for b in (OUT / "feed_sample.txt").read_text(encoding="utf-8").split("\n\n") if b.strip()]
    seen = set()
    for b in blocks:
        lines = b.splitlines()
        if lines[0].startswith(":"):
            continue                                   # keep-alive comment
        assert lines[0].startswith("event: ") and lines[1].startswith("data: ")
        seen.add(lines[0][7:])
        json.loads(lines[1][6:])
    assert seen == FEED_TYPES
