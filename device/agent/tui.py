"""Status screen for the agent (A-T06): a live panel refreshed 4 times a second.

Shows meter/venue/mode, mic level, the last window, what was sent, the queue,
the last acked seq, clock skew, network state and the last error.
Everything shown is read from the live objects: no extra state is kept here.
"""
import threading
from typing import Optional

from rich.console import Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

BAR_WIDTH = 30


def _level_bar(db: Optional[float]) -> Text:
    """Loudness -100..0 dBFS as a bar."""
    if db is None:
        return Text("-" * BAR_WIDTH, style="dim")
    frac = min(1.0, max(0.0, (db + 100.0) / 100.0))
    filled = int(round(frac * BAR_WIDTH))
    return Text("#" * filled + "-" * (BAR_WIDTH - filled) + f"  {db:.1f} dBFS", style="green")


class StatusScreen:
    def __init__(self, meter_cfg: dict, mode: str, input_spec: str, uploader, outbox, refresh_hz: float = 4.0):
        self.cfg = meter_cfg
        self.mode = mode
        self.input_spec = input_spec
        self.uploader = uploader
        self.outbox = outbox
        self.refresh_hz = refresh_hz
        self.captured = 0          # windows made from the audio
        self.last_window = None    # (start_iso, peaks, loudness)
        self.last_seq = None

    def note_window(self, seq: int, start_iso: str, peaks: int, loudness: float) -> None:
        self.captured += 1
        self.last_seq = seq
        self.last_window = (start_iso, peaks, loudness)

    def render(self) -> Panel:
        up = self.uploader
        grid = Table.grid(padding=(0, 2))
        grid.add_column(justify="right", style="bold")
        grid.add_column()
        grid.add_row("meter", f"{self.cfg['meter_id']}  venue {self.cfg['venue_id']}")
        grid.add_row("mode / input", f"{self.mode}  /  {self.input_spec}")
        grid.add_row("mic level", _level_bar(self.last_window[2] if self.last_window else None))
        if self.last_window:
            start, peaks, loud = self.last_window
            grid.add_row("last window", f"seq {self.last_seq}  {start}  peaks {peaks}")
        else:
            grid.add_row("last window", "waiting for the first 10 s window")
        grid.add_row("windows made", str(self.captured))
        grid.add_row("sent (acked)", f"{up.acked}   last ack seq {up.last_ack_seq}")
        grid.add_row("queued", f"{self.outbox.count()}   parked {len(up.parked)}   dead {self.outbox.dead_count()}")
        skew = "-" if up.skew_s is None else f"{up.skew_s:+.2f} s"
        grid.add_row("clock skew", skew)
        grid.add_row("network", up.network_state)
        grid.add_row("last error", up.last_error or "none")
        return Panel(Group(grid), title="SoundProof agent", border_style="cyan")


class StatusLoop:
    """Runs the status screen in its own thread until stop() is called."""

    def __init__(self, screen: StatusScreen):
        self.screen = screen
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def _run(self) -> None:
        with Live(self.screen.render(), refresh_per_second=self.screen.refresh_hz, transient=False) as live:
            while not self._stop.is_set():
                live.update(self.screen.render())
                self._stop.wait(1.0 / self.screen.refresh_hz)
            live.update(self.screen.render())

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)
