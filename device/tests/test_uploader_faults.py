"""Fault tests for the uploader (fixes for the auth-block, bulk-422 and bad-response bugs)."""
import threading

from device.agent.outbox import Outbox
from device.agent.uploader import Uploader

CFG = {"meter_id": "M-07", "venue_id": "V-BUEA-CIMFEST", "fw": "agent-0.1.0"}
SEED = bytes(range(32))


class Resp:
    def __init__(self, code, body=None, text=None):
        self.status_code = code
        self._body = body
        self._text = text

    def json(self):
        if self._text is not None:
            raise ValueError("not json")
        return self._body


class Server:
    """Stub SONACAM. Options: refuse_single (dict seq -> code), bulk_422, bulk_text, raise_once."""

    def __init__(self, refuse_single=None, bulk_422=False, bulk_text=False, raise_once=False):
        self.refuse_single = refuse_single or {}
        self.bulk_422 = bulk_422
        self.bulk_text = bulk_text
        self.raise_once = raise_once
        self.received = []

    def post(self, path, json=None, timeout=None):
        if self.raise_once:
            self.raise_once = False
            raise RuntimeError("boom")
        if path == "/v1/batches":
            seq = json["seq"]
            self.received.append(seq)
            code = self.refuse_single.get(seq, 200)
            if code == 200:
                return Resp(200, {"ack": seq, "status": "stored"})
            return Resp(code, {"error": "x"})
        if path == "/v1/batches/bulk":
            if self.bulk_422:
                return Resp(422, {"error": "invalid"})
            if self.bulk_text:
                return Resp(200, text="<html>proxy</html>")
            return Resp(200, {"results": [{"seq": b["seq"], "status": "stored"} for b in json["batches"]]})
        if path == "/v1/heartbeat":
            return Resp(200, {"ok": True, "server_time": "2026-11-24T00:00:00.000Z"})
        raise AssertionError(path)


def _outbox(tmp_path, n):
    ob = Outbox(str(tmp_path / "o.db"))
    for s in range(1, n + 1):
        ob.put({"seq": s, "meter_id": "M-07", "sig": "x", "peaks_b64": ""})
    return ob


def _uploader(ob, server):
    return Uploader(ob, server, CFG, SEED, sleep=lambda s: None, rand=lambda: 0.5)


def test_refused_batch_does_not_block_the_queue(tmp_path):
    ob = _outbox(tmp_path, 5)
    server = Server(refuse_single={1: 401})
    up = _uploader(ob, server)
    for _ in range(10):
        up.drain_once()
    # batch 1 is parked; 2..5 went through
    assert [s for s, _, _ in ob.peek(10)] == [1]
    assert up.acked == 4
    assert up.network_state == "OK"          # an auth refusal is not a network failure


def test_parked_batch_is_retried_when_nothing_else_is_left(tmp_path):
    ob = _outbox(tmp_path, 2)
    server = Server(refuse_single={1: 401})
    up = _uploader(ob, server)
    for _ in range(6):
        up.drain_once()
    assert [s for s, _, _ in ob.peek(10)] == [1]
    assert server.received.count(1) >= 2     # tried again after the rest was done


def test_bulk_422_isolates_the_bad_batch(tmp_path):
    ob = _outbox(tmp_path, 15)               # >10, so the bulk path is used first
    server = Server(bulk_422=True, refuse_single={3: 422})
    up = _uploader(ob, server)
    for _ in range(40):
        up.drain_once()
    assert ob.count() == 0                   # the queue drained
    assert ob.dead_count() == 1              # only batch 3 is dead
    assert up.acked == 14


def test_non_json_bulk_response_does_not_stop_the_queue(tmp_path):
    ob = _outbox(tmp_path, 15)
    server = Server(bulk_text=True)
    up = _uploader(ob, server)
    up.drain_once()                          # must not raise
    assert ob.count() == 15                  # nothing lost, nothing acked
    assert up.failures >= 1                  # counted as a network-level failure
    assert "not the expected JSON" in (up.last_error or "")


def test_run_loop_survives_an_unexpected_error(tmp_path):
    ob = _outbox(tmp_path, 3)
    server = Server(raise_once=True)
    up = _uploader(ob, server)
    stop = threading.Event()
    t = threading.Thread(target=up.run, args=(stop, 0.01))
    t.start()
    for _ in range(200):                     # wait up to ~2 s for the batches to go out
        if ob.count() == 0:
            break
        threading.Event().wait(0.01)
    alive = t.is_alive()
    stop.set()
    t.join(timeout=2)
    assert alive                             # the thread survived the RuntimeError
    assert ob.count() == 0                   # and it still drained the queue
    assert up.network_state == "OK"          # a later successful send clears the failure state
