"""Live-feed bus: Postgres NOTIFY (from any container) → api process → every open SSE connection.

A background thread holds one LISTEN connection (plain sync psycopg: works on Linux and on the Windows host) and
hands each notification to the asyncio loop, which copies it into every subscriber's queue. Slow subscribers lose
their oldest events instead of blocking everyone. The thread reconnects if the db restarts.
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
from typing import Any, Optional

import psycopg

from server import config
from server.db import EVENTS_CHANNEL

log = logging.getLogger(__name__)
QUEUE_MAX = 200


class EventBus:
    def __init__(self) -> None:
        self._subs: set[asyncio.Queue] = set()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.ready = threading.Event()  # set once LISTEN is active (tests wait on it)

    # ---------------------------------------------------------------- subscribers (asyncio side)
    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_MAX)
        self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subs.discard(q)

    def publish(self, event: dict[str, Any]) -> None:
        for q in list(self._subs):
            if q.full():
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            q.put_nowait(event)

    # ---------------------------------------------------------------- listener thread
    def start(self, loop: asyncio.AbstractEventLoop, url: Optional[str] = None) -> None:
        self._loop = loop
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, args=(url,), name="sp-events-listener", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)

    def _run(self, url: Optional[str]) -> None:
        while not self._stop.is_set():
            try:
                with psycopg.connect(url or config.DATABASE_URL, autocommit=True) as conn:
                    conn.execute(f"LISTEN {EVENTS_CHANNEL}")
                    self.ready.set()
                    log.info("listening on %s", EVENTS_CHANNEL)
                    while not self._stop.is_set():
                        for n in conn.notifies(timeout=1.0):
                            try:
                                event = json.loads(n.payload)
                            except json.JSONDecodeError:
                                log.error("bad event payload: %r", n.payload[:200])
                                continue
                            self._loop.call_soon_threadsafe(self.publish, event)
            except psycopg.Error as e:
                self.ready.clear()
                log.warning("event listener lost the db (%s); retrying in 2 s", e)
                self._stop.wait(2)


bus = EventBus()
