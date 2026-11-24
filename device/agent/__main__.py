"""Agent runner (A-T06): capture -> window -> batch -> outbox -> uploader, with a live status screen.

  python -m device.agent run --config device\\config\\M-07.toml [--mode demo|field] [--input mic|file:<path>]

Stop with Ctrl+C. Everything unsent stays in the outbox (device/state/) and is sent on the next start.
run_pipeline() is shared with the virtual meters (device/virtual).
"""
import argparse
import os
import sys
import threading
import tomllib
from datetime import datetime, timezone

import httpx

from device.agent.batcher import build_batch
from device.agent.capture import FileSource, MicSource
from device.agent.eventlog import EventLog
from device.agent.outbox import Outbox
from device.agent.scheduler import Scheduler
from device.agent.state import MeterState
from device.agent.tui import StatusLoop, StatusScreen
from device.agent.uploader import Uploader
from device.tools.provision import load_seed

STATE_DIR = os.path.join("device", "state")


def _parse(argv):
    p = argparse.ArgumentParser(prog="device.agent")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run the meter agent")
    r.add_argument("--config", required=True, help="path to device/config/<meter>.toml")
    r.add_argument("--mode", choices=["demo", "field"], default=None, help="overrides the config value")
    r.add_argument("--input", default=None, help="'mic' or 'file:<path>'; overrides the config value")
    return p.parse_args(argv)


def _blocks(input_spec: str):
    if input_spec == "mic":
        return MicSource().blocks()
    if input_spec.startswith("file:"):
        # realtime: play the file at its own speed, like a live meter
        return FileSource(input_spec[len("file:"):], realtime=True).blocks()
    raise SystemExit(f"input must be 'mic' or 'file:<path>', got {input_spec!r}")


def _wait_for_empty_outbox(outbox, timeout_s: float) -> None:
    import time
    end = time.monotonic() + timeout_s
    while outbox.count() > 0 and time.monotonic() < end:
        time.sleep(0.1)


def run_pipeline(cfg: dict, mode: str, blocks, input_label: str, state_dir: str = STATE_DIR,
                 show_screen: bool = True, client=None, drain_timeout_s: float = 60.0) -> int:
    """Send every window from `blocks` as signed batches. Returns the number of windows made."""
    meter = cfg["meter_id"]
    os.makedirs(state_dir, exist_ok=True)
    seed = load_seed(meter)
    state = MeterState(meter, state_dir)
    outbox = Outbox(os.path.join(state_dir, f"{meter}_outbox.db"))
    own_client = client is None
    if own_client:
        client = httpx.Client(base_url=cfg["sonacam_url"])
    events = EventLog(os.path.join(state_dir, f"{meter}_events.jsonl"))
    uploader = Uploader(outbox, client, cfg, seed, heartbeat_s=float(cfg.get("heartbeat_s", 60)), log=events.append)
    screen = StatusScreen(cfg, mode, input_label, uploader, outbox)

    stop = threading.Event()
    worker = threading.Thread(target=uploader.run, args=(stop,), daemon=True)
    worker.start()
    view = None
    if show_screen:
        view = StatusLoop(screen)
        view.start()

    made = 0
    finished = False
    try:
        for win in Scheduler(mode).windows(blocks):
            seq = state.next_seq()
            batch = build_batch(cfg, seq, win.start_utc, win.peaks, win.loudness_db, seed)
            outbox.put(batch)
            stamp = datetime.fromtimestamp(win.start_utc, tz=timezone.utc).isoformat(timespec="seconds")
            events.append("window", seq=seq, window_start=batch["window_start"], peaks=int(win.peaks.size),
                          loudness_db=win.loudness_db, input=input_label)
            screen.note_window(seq, stamp, int(win.peaks.size), win.loudness_db)
            made += 1
        finished = True
    except KeyboardInterrupt:
        pass
    finally:
        if finished:
            # the audio ended normally: send what is queued before stopping (a Ctrl+C does not wait)
            _wait_for_empty_outbox(outbox, drain_timeout_s)
        if view is not None:
            view.stop()
        stop.set()
        worker.join(timeout=10)
        if own_client:
            client.close()
    return made


def run(argv=None) -> int:
    args = _parse(argv)
    with open(args.config, "rb") as fh:
        cfg = tomllib.load(fh)
    mode = args.mode or cfg.get("mode", "demo")
    input_spec = args.input or cfg.get("input", "mic")
    run_pipeline(cfg, mode, _blocks(input_spec), input_spec)
    return 0


if __name__ == "__main__":
    sys.exit(run())
