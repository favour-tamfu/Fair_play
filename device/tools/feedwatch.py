"""Watch B's live feed (SSE) and save what it says: batch, match, play, meter, ledger events.

Runs in a background thread inside the monitor. Each event is saved as one JSON line in
device/state/<meter>_feed.jsonl, with the time it was received.
"""
import json
import os
import threading
import time
from datetime import datetime, timezone
from typing import Iterable, Iterator, Optional, Tuple

import httpx


def parse_sse(lines: Iterable[str]) -> Iterator[Tuple[str, dict]]:
    """Turn SSE text lines into (event_name, data_dict) pairs. Comment lines are skipped."""
    event = "message"
    data_parts = []
    for raw in lines:
        line = raw.rstrip("\r\n")
        if line == "":
            if data_parts:
                try:
                    yield event, json.loads("\n".join(data_parts))
                except ValueError:
                    pass
            event, data_parts = "message", []
        elif line.startswith(":"):
            continue
        elif line.startswith("event:"):
            event = line[len("event:"):].strip()
        elif line.startswith("data:"):
            data_parts.append(line[len("data:"):].lstrip())


class FeedWatcher:
    def __init__(self, base_url: str, out_path: str, retry_s: float = 5.0):
        self.url = base_url.rstrip("/") + "/api/v1/feed"
        self.out_path = out_path
        self.retry_s = retry_s
        self.connected = False
        self.last_error: Optional[str] = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _save(self, kind: str, data: dict) -> None:
        rec = {"t": datetime.now(timezone.utc).isoformat(timespec="milliseconds"), "kind": kind, **data}
        with open(self.out_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                with httpx.stream("GET", self.url, timeout=None) as resp:
                    self.connected = True
                    self.last_error = None
                    for kind, data in parse_sse(resp.iter_lines()):
                        if self._stop.is_set():
                            return
                        if kind in ("batch", "match", "play", "meter", "ledger", "flag", "stats"):
                            self._save(kind, data)
            except Exception as exc:  # network drop, server restart: note it and try again
                self.connected = False
                self.last_error = f"{type(exc).__name__}: {exc}"
            time.sleep(self.retry_s)
