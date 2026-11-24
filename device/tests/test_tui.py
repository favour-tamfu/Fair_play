"""Tests for the status screen (A-T06): it renders what the agent reports."""
import io
from types import SimpleNamespace

from rich.console import Console

from device.agent.tui import StatusScreen


class _Outbox:
    def __init__(self, n, dead):
        self._n, self._dead = n, dead

    def count(self):
        return self._n

    def dead_count(self):
        return self._dead


def _text(panel) -> str:
    buf = io.StringIO()
    Console(file=buf, width=110, record=False, color_system=None).print(panel)
    return buf.getvalue()


def _uploader(**kw):
    base = dict(acked=3, last_ack_seq=3, parked=set(), skew_s=None, network_state="OK", last_error=None)
    base.update(kw)
    return SimpleNamespace(**base)


CFG = {"meter_id": "M-07", "venue_id": "V-BUEA-CIMFEST"}


def test_waiting_before_the_first_window():
    screen = StatusScreen(CFG, "demo", "mic", _uploader(acked=0, last_ack_seq=None), _Outbox(0, 0))
    out = _text(screen.render())
    assert "M-07" in out and "V-BUEA-CIMFEST" in out
    assert "waiting for the first 10 s window" in out
    assert "network" in out and "OK" in out


def test_window_and_queue_are_shown():
    up = _uploader(acked=5, last_ack_seq=5, parked={7}, skew_s=0.25, network_state="RETRYING", last_error="http 503")
    screen = StatusScreen(CFG, "demo", "file:x.wav", up, _Outbox(4, 1))
    screen.note_window(9, "2026-11-24T00:30:00+00:00", 88, -21.5)
    out = _text(screen.render())
    assert "seq 9" in out and "peaks 88" in out
    assert "-21.5 dBFS" in out
    assert "last ack seq 5" in out
    assert "queued" in out and "4" in out and "parked 1" in out and "dead 1" in out
    assert "+0.25 s" in out
    assert "RETRYING" in out and "http 503" in out


def test_mic_bar_is_empty_without_a_window_and_filled_with_loud_audio():
    screen = StatusScreen(CFG, "demo", "mic", _uploader(), _Outbox(0, 0))
    assert "-" * 30 in _text(screen.render())
    screen.note_window(1, "t", 10, 0.0)      # full scale
    assert "#" * 30 in _text(screen.render())
