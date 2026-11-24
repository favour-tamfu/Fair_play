"""Event log for the agent: one JSON line per event, appended to device/state/<meter>_events.jsonl.

Events: window (a batch was built), acked (server stored it), parked, dead, error, network.
The monitor (device/tools/monitor.py) reads this file to show what was recorded and sent.
"""
import json
import os
import threading
from datetime import datetime, timezone


class EventLog:
    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    def append(self, event: str, **fields) -> None:
        rec = {"t": datetime.now(timezone.utc).isoformat(timespec="milliseconds"), "event": event, **fields}
        line = json.dumps(rec, ensure_ascii=False)
        with self._lock, open(self.path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def read(self, limit: int = 5000) -> list:
        if not os.path.exists(self.path):
            return []
        with open(self.path, "r", encoding="utf-8") as fh:
            lines = fh.readlines()[-limit:]
        out = []
        for line in lines:
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
        return out
