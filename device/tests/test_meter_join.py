"""FairPlayMeter: zero-question setup, asks SONACAM to join (signed with its own key), waits for approval, then listens
in the background behind a small menu."""
import builtins
import json
import os
import re
import time

import numpy as np
import pytest

from device.packaging import meter_app
from fairplay_core.signing import verify_dict


class Resp:
    def __init__(self, code, body):
        self.status_code, self._body, self.text = code, body, json.dumps(body)

    def json(self):
        return self._body


@pytest.fixture
def here(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(meter_app, "DEFAULT_SONACAM", "https://sonacam.example")
    monkeypatch.setattr(meter_app.time, "sleep", lambda s: None)
    return tmp_path


def fake_server(monkeypatch, join, heartbeat=((404, {"error": "unknown_meter"}),)):
    """join / heartbeat: answers in turn (the last one repeats). Records what the meter sent."""
    import httpx
    join, heartbeat, sent = list(join), list(heartbeat), []

    def post(url, json=None, timeout=None):
        sent.append((url, json))
        q = join if url.endswith("/v1/meters/join") else heartbeat
        code, body = q.pop(0) if len(q) > 1 else q[0]
        if isinstance(body, Exception):
            raise body
        return Resp(code, body)
    monkeypatch.setattr(httpx, "post", post)
    return sent


def test_setup_asks_nothing(here, monkeypatch):
    monkeypatch.setattr(builtins, "input", lambda *a: pytest.fail("setup must not ask anything"))
    cfg = meter_app.setup(quiet=True)
    assert re.fullmatch(r"M-\d{4}", cfg["meter_id"]) and cfg["venue_id"] == meter_app.DEFAULT_VENUE
    assert cfg["sonacam_url"] == "https://sonacam.example"
    assert os.path.exists(os.path.join("device", "secrets", f"{cfg['meter_id']}.seed"))


def test_join_request_is_signed_by_the_meters_own_key(here, monkeypatch):
    cfg = meter_app.setup(quiet=True)
    sent = fake_server(monkeypatch, [(202, {"status": "pending"})])
    assert meter_app.ask_to_join(cfg) == ("pending", "HTTP 202")
    url, body = sent[0]
    assert url == "https://sonacam.example/v1/meters/join" and body["computer"]
    assert body["device_id"] == meter_app.device_id() and len(body["device_id"]) == 32     # same id every time
    assert verify_dict(meter_app._pub_key(cfg["meter_id"]), body)                          # device id is signed too


def test_waits_until_approved_then_remembers(here, monkeypatch, capsys):
    cfg = meter_app.setup(quiet=True)
    sent = fake_server(monkeypatch, [(202, {"status": "pending"})] * 2 + [(200, {"status": "approved"})])
    assert meter_app.wait_for_approval(cfg) == cfg
    out = capsys.readouterr().out
    assert "Waiting for approval from SONACAM" in out and meter_app.key_fingerprint(sent[0][1]["public_key_b64"]) in out
    assert "APPROVED by SONACAM" in out and len(sent) == 3
    sent.clear()
    assert meter_app.wait_for_approval(cfg) == cfg and sent == []      # approved before: starts even offline


def test_rejected_does_not_listen(here, monkeypatch):
    cfg = meter_app.setup(quiet=True)
    fake_server(monkeypatch, [(403, {"status": "rejected"})])
    assert meter_app.wait_for_approval(cfg) is None


def test_taken_id_picks_another_by_itself(here, monkeypatch):
    cfg = meter_app.setup(meter="M-2000", quiet=True)
    fake_server(monkeypatch, [(409, {"error": "meter_id_taken", "detail": "x"}), (200, {"status": "approved"})])
    new = meter_app.wait_for_approval(cfg)
    assert new["meter_id"] != "M-2000" and new["venue_id"] == cfg["venue_id"]
    assert not os.path.exists(meter_app._cfg_path("M-2000")) and os.path.exists(meter_app._cfg_path(new["meter_id"]))


def test_computer_that_already_asked_waits(here, monkeypatch, capsys):
    cfg = meter_app.setup(quiet=True)
    fake_server(monkeypatch, [(409, {"error": "device_already_waiting", "meter": "M-3000",
                                     "detail": "this computer already asked to join as M-3000"}),
                              (200, {"status": "approved"})])
    assert meter_app.wait_for_approval(cfg) == cfg                           # waited, did not make a new request id
    assert "already asked to join as M-3000" in capsys.readouterr().out


def test_every_copy_on_a_computer_shares_one_meter(tmp_path, monkeypatch):
    monkeypatch.setattr(meter_app.sys, "frozen", True, raising=False)
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path / "pd"))
    for copy in ("a", "b"):
        monkeypatch.setattr(meter_app, "APP_DIR", str(tmp_path / copy))
        assert meter_app.data_dir() == str(tmp_path / "pd" / "FairPlayMeter")
    old = tmp_path / "old" / "device" / "config"                             # a meter set up next to an older exe
    old.mkdir(parents=True)
    (old / "M-21.toml").write_text("meter_id = 'M-21'\n")
    monkeypatch.setattr(meter_app, "APP_DIR", str(tmp_path / "old"))
    assert meter_app.data_dir() == str(tmp_path / "old")


def test_older_server_is_asked_through_the_heartbeat(here, monkeypatch, capsys):
    cfg = meter_app.setup(quiet=True)
    sent = fake_server(monkeypatch, [(405, {"detail": "Method Not Allowed"})],
                       [(404, {"error": "unknown_meter"}), (200, {"ok": True})])
    assert meter_app.wait_for_approval(cfg) == cfg
    hb = [b for u, b in sent if u.endswith("/v1/heartbeat")]
    assert len(hb) == 2 and verify_dict(meter_app._pub_key(cfg["meter_id"]), hb[0])
    assert "Register a meter" in capsys.readouterr().out                 # says how to register by hand


def test_menu_listens_in_background_pauses_and_stops(here, monkeypatch, capsys):
    import device.agent.__main__ as agent
    cfg = meter_app.setup(url="http://127.0.0.1:9", quiet=True)          # closed port: sending just fails and waits

    def blocks(spec):                                                     # a quiet fake microphone, 0.1 s blocks
        while True:
            time.sleep(0.005)
            yield time.time(), np.zeros(4800, dtype=np.float32)
    monkeypatch.setattr(agent, "_blocks", blocks)
    lst = meter_app.Listener(cfg).start()
    deadline = time.time() + 10
    while lst.screen is None and time.time() < deadline:
        time.sleep(0.05)
    answers = iter(["1", "2", "1", "2", "4", "9", "5"])
    monkeypatch.setattr(builtins, "input", lambda *a: next(answers))
    meter_app.menu(cfg, lst)
    out = capsys.readouterr().out
    assert "Listening in the background" in out and "State            listening" in out
    assert "State            paused" in out and "Listening again" in out
    assert cfg["meter_id"] in out and "Type a number" in out and "Stopped" in out
    assert not lst.thread.is_alive() and lst.error is None


def test_fingerprint_matches_the_server():
    import hashlib
    k = "rXGnqC6huyGes3lZJHbKObxbP+/zC027Osd5RorRQsw="
    h = hashlib.sha256(k.encode()).hexdigest()[:16]
    assert meter_app.key_fingerprint(k) == " ".join(h[i:i + 4] for i in range(0, 16, 4))
