"""Tests for the outbox (A-T05): durable, ack-before-delete, dead table."""
import os

import pytest

from device.agent.outbox import Outbox
from device.agent.state import MeterState


def _b(seq):
    return {"seq": seq, "meter_id": "M-97", "sig": f"sig-{seq}", "peaks_b64": "AAAA"}


@pytest.fixture
def db(tmp_path):
    # Same SQLite file as MeterState, as the plan requires.
    MeterState("M-97", state_dir=str(tmp_path))
    return os.path.join(str(tmp_path), "M-97.db")


def test_put_peek_ack_in_seq_order(db):
    ob = Outbox(db)
    for s in (3, 1, 2):
        ob.put(_b(s))
    assert [seq for seq, _, _ in ob.peek(10)] == [1, 2, 3]
    ob.ack(2)
    assert [seq for seq, _, _ in ob.peek(10)] == [1, 3]
    assert ob.count() == 2


def test_outbox_survives_restart(db):
    ob = Outbox(db)
    ob.put(_b(1))
    ob.put(_b(2))
    restarted = Outbox(db)  # new process
    assert restarted.count() == 2
    assert restarted.peek(1)[0][1]["sig"] == "sig-1"


def test_record_error_increments_attempts(db):
    ob = Outbox(db)
    ob.put(_b(1))
    ob.record_error(1, "http 401")
    ob.record_error(1, "http 401")
    seq, batch, attempts = ob.peek(1)[0]
    assert attempts == 2


def test_to_dead_moves_and_keeps_content(db):
    ob = Outbox(db)
    ob.put(_b(5))
    ob.to_dead(5, "http 409")
    assert ob.count() == 0
    assert ob.dead_count() == 1


def test_nothing_removed_without_ack(db):
    ob = Outbox(db)
    ob.put(_b(1))
    ob.record_error(1, "boom")
    assert ob.count() == 1
