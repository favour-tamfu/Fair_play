"""FairPlayMeter asks SONACAM to join (signed with its own key) and waits for approval before listening."""
import json
import os

import pytest

from device.packaging import meter_app
from device.tools.provision import provision
from fairplay_core.signing import verify_dict


class Resp:
    def __init__(self, code, body):
        self.status_code, self._body, self.text = code, body, json.dumps(body)

    def json(self):
        return self._body


@pytest.fixture
def meter(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    provision("M-41", "V-BUEA-CIMFEST", force=True)
    return {"meter_id": "M-41", "venue_id": "V-BUEA-CIMFEST", "sonacam_url": "https://sonacam.example"}


def fake_server(monkeypatch, answers):
    """answers: list of (code, body) returned in turn; records what the meter sent."""
    import httpx
    sent = []

    def post(url, json=None, timeout=None):
        sent.append((url, json))
        code, body = answers.pop(0) if len(answers) > 1 else answers[0]
        if isinstance(body, Exception):
            raise body
        return Resp(code, body)
    monkeypatch.setattr(httpx, "post", post)
    monkeypatch.setattr(meter_app.time, "sleep", lambda s: None)
    return sent


def test_request_is_signed_by_the_meters_own_key(meter, monkeypatch):
    sent = fake_server(monkeypatch, [(202, {"status": "pending"})])
    assert meter_app.ask_to_join(meter) == ("pending", "HTTP 202")
    url, body = sent[0]
    assert url == "https://sonacam.example/v1/meters/join"
    with open(os.path.join("contract", "meters", "M-41.pub.json"), encoding="utf-8") as fh:
        pub = json.load(fh)
    assert body["public_key_b64"] == pub["public_key_b64"] and body["computer"]
    assert verify_dict(pub["public_key_b64"], body)
    assert not os.path.exists(os.path.join("contract", "meters", "M-41.seed"))
    assert "seed" not in json.dumps(body)


def test_waits_until_approved(meter, monkeypatch, capsys):
    sent = fake_server(monkeypatch, [(202, {"status": "pending"}), (202, {"status": "pending"}),
                                     (200, {"status": "approved"})])
    assert meter_app.wait_for_approval(meter) is True
    assert len(sent) == 3
    out = capsys.readouterr().out
    assert meter_app.key_fingerprint(sent[0][1]["public_key_b64"]) in out and "Approved" in out


def test_rejected_or_taken_does_not_listen(meter, monkeypatch):
    fake_server(monkeypatch, [(403, {"status": "rejected"})])
    assert meter_app.wait_for_approval(meter) is False
    fake_server(monkeypatch, [(409, {"error": "meter_id_taken", "detail": "M-41 belongs to another meter"})])
    assert meter_app.wait_for_approval(meter) is False


def test_unreachable_or_old_server_still_starts(meter, monkeypatch):
    fake_server(monkeypatch, [(0, ConnectionError("down"))])
    assert meter_app.wait_for_approval(meter) is True                 # reports wait in the outbox
    fake_server(monkeypatch, [(404, {"detail": "Not Found"})])
    assert meter_app.ask_to_join(meter)[0] == "old_server"
    fake_server(monkeypatch, [(405, {"detail": "Method Not Allowed"})])    # seen live on a server without the join step
    assert meter_app.ask_to_join(meter)[0] == "old_server"


def test_fingerprint_matches_the_server():
    # same as server/registry.key_fingerprint (copied here: the exe does not ship the server)
    import hashlib
    k = "rXGnqC6huyGes3lZJHbKObxbP+/zC027Osd5RorRQsw="
    h = hashlib.sha256(k.encode()).hexdigest()[:16]
    assert meter_app.key_fingerprint(k) == " ".join(h[i:i + 4] for i in range(0, 16, 4))
