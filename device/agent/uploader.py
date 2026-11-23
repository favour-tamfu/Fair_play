"""Uploader and heartbeat (A-T05). Implements the device side of contract 01 §4.

Rules:
  - never delete a batch before the server acks it (ack or 'duplicate')
  - 401 bad_signature and 404 unknown_meter: keep the batch, record the error, back off
  - 409 seq_conflict and 422 invalid: move the batch to the dead table
  - 5xx, timeouts, connection errors: keep the batch, back off 1,2,4,8,16,30 s with +-20% jitter
  - bulk (<=50 per request) when more than 10 batches wait, single POST otherwise
  - heartbeat every heartbeat_s seconds, signed like a batch; its server_time gives clock skew
"""
import base64
import random
import time
from datetime import datetime, timezone
from typing import Callable, Optional

import httpx

from device.agent.batcher import sign_fields
from device.agent.outbox import Outbox

RETRY_S = (1, 2, 4, 8, 16, 30)
BULK_THRESHOLD = 10
BULK_MAX = 50
KEEP_CODES = {401, 404}
DEAD_CODES = {409, 422}
DEAD_REASONS = {"seq_conflict", "invalid"}
KEEP_REASONS = {"bad_signature", "unknown_meter"}
TIMEOUT_S = 5.0


def _utc_now_iso(epoch: Optional[float] = None) -> str:
    dt = datetime.fromtimestamp(time.time() if epoch is None else epoch, tz=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


class Uploader:
    def __init__(
        self,
        outbox: Outbox,
        client,
        meter_cfg: dict,
        seed: bytes,
        heartbeat_s: float = 60.0,
        sleep: Callable[[float], None] = time.sleep,
        rand: Callable[[], float] = random.random,
    ):
        self.outbox = outbox
        self.client = client
        self.cfg = meter_cfg
        self.seed = seed
        self.heartbeat_s = heartbeat_s
        self.sleep = sleep
        self.rand = rand
        self.failures = 0          # consecutive failed rounds, drives backoff
        self.acked = 0
        self.last_error: Optional[str] = None
        self.skew_s: Optional[float] = None
        self.last_heartbeat = 0.0

    @property
    def network_state(self) -> str:
        if self.failures == 0:
            return "OK"
        return "RETRYING" if self.failures < 3 else "DOWN"

    def _backoff(self) -> None:
        base = RETRY_S[min(self.failures, len(RETRY_S) - 1)]
        self.failures += 1
        self.sleep(base * (0.8 + 0.4 * self.rand()))

    def _post(self, path: str, payload: dict):
        try:
            return self.client.post(path, json=payload, timeout=TIMEOUT_S)
        except (httpx.HTTPError, OSError) as exc:
            self.last_error = f"{type(exc).__name__}"
            return None

    def drain_once(self) -> bool:
        """One round of sending. Returns True if the round made progress or the outbox is empty."""
        if self.outbox.count() == 0:
            return True
        if self.outbox.count() > BULK_THRESHOLD:
            return self._drain_bulk()
        return self._drain_single()

    def _drain_single(self) -> bool:
        rows = self.outbox.peek(1)
        if not rows:
            return True
        seq, batch, _ = rows[0]
        resp = self._post("/v1/batches", batch)
        if resp is None or resp.status_code >= 500:
            self.last_error = self.last_error or f"http {getattr(resp, 'status_code', 'timeout')}"
            self._backoff()
            return False
        code = resp.status_code
        if code == 200:
            self.outbox.ack(seq)
            self.acked += 1
            self.failures = 0
            self.last_error = None
            return True
        if code in KEEP_CODES:
            self.outbox.record_error(seq, f"http {code}")
            self.last_error = f"http {code}"
            self._backoff()
            return False
        if code in DEAD_CODES:
            self.outbox.to_dead(seq, f"http {code}")
            self.last_error = f"http {code} moved to dead"
            return True
        self.outbox.record_error(seq, f"http {code}")
        self._backoff()
        return False

    def _drain_bulk(self) -> bool:
        rows = self.outbox.peek(BULK_MAX)
        if not rows:
            return True
        by_seq = {seq: (batch, att) for seq, batch, att in rows}
        resp = self._post("/v1/batches/bulk", {"batches": [b for _, b, _ in rows]})
        if resp is None or resp.status_code >= 500 or resp.status_code == 422:
            self.last_error = self.last_error or f"bulk http {getattr(resp, 'status_code', 'timeout')}"
            self._backoff()
            return False
        if resp.status_code != 200:
            self.last_error = f"bulk http {resp.status_code}"
            self._backoff()
            return False
        progressed = False
        for item in resp.json().get("results", []):
            seq = item.get("seq")
            if seq not in by_seq:
                continue
            status = item.get("status")
            if status in ("stored", "duplicate"):
                self.outbox.ack(seq)
                self.acked += 1
                progressed = True
            elif item.get("error") in DEAD_REASONS:
                self.outbox.to_dead(seq, item.get("error"))
            else:  # bad_signature, unknown_meter, anything else: keep and retry later
                self.outbox.record_error(seq, str(item.get("error")))
                self.last_error = str(item.get("error"))
        if progressed:
            self.failures = 0
            self.last_error = None
        else:
            self._backoff()
            return False
        return True

    def send_heartbeat(self, now: Optional[float] = None) -> Optional[float]:
        """Signed heartbeat. Returns clock skew in seconds (server_time - local) or None."""
        now = time.time() if now is None else now
        hb = {
            "meter_id": self.cfg["meter_id"],
            "venue_id": self.cfg["venue_id"],
            "sent_at": _utc_now_iso(now),
            "queued": self.outbox.count(),
            "fw": self.cfg.get("fw", "agent-0.1.0"),
        }
        hb["sig"] = sign_fields(self.seed, hb)
        self.last_heartbeat = now
        resp = self._post("/v1/heartbeat", hb)
        if resp is None or resp.status_code != 200:
            return None
        server_time = resp.json().get("server_time")
        if not server_time:
            return None
        server_epoch = datetime.strptime(server_time, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc).timestamp()
        self.skew_s = server_epoch - now
        return self.skew_s

    def maybe_heartbeat(self, now: Optional[float] = None) -> Optional[float]:
        now = time.time() if now is None else now
        if now - self.last_heartbeat >= self.heartbeat_s:
            return self.send_heartbeat(now)
        return None

    def run(self, stop_event, idle_s: float = 0.5) -> None:
        """Thread body: heartbeat when due, drain the outbox, wait briefly when idle."""
        while not stop_event.is_set():
            self.maybe_heartbeat()
            if self.outbox.count() == 0:
                stop_event.wait(idle_s)
                continue
            self.drain_once()
