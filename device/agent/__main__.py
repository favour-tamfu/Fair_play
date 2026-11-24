"""Agent runner (A-T06): capture -> window -> batch -> outbox -> uploader, with a live status screen.

  python -m device.agent run --config device\\config\\M-07.toml [--mode demo|field] [--input mic|file:<path>]

Stop with Ctrl+C. Everything unsent stays in the outbox (device/state/) and is sent on the next start.
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


def run(argv=None) -> int:
    args = _parse(argv)
    with open(args.config, "rb") as fh:
        cfg = tomllib.load(fh)
    mode = args.mode or cfg.get("mode", "demo")
    input_spec = args.input or cfg.get("input", "mic")
    meter = cfg["meter_id"]

    os.makedirs(STATE_DIR, exist_ok=True)
    seed = load_seed(meter)
    state = MeterState(meter)
    outbox = Outbox(os.path.join(STATE_DIR, f"{meter}_outbox.db"))
    client = httpx.Client(base_url=cfg["sonacam_url"])
    events = EventLog(os.path.join(STATE_DIR, f"{meter}_events.jsonl"))
    uploader = Uploader(outbox, client, cfg, seed, heartbeat_s=float(cfg.get("heartbeat_s", 60)), log=events.append)
    screen = StatusScreen(cfg, mode, input_spec, uploader, outbox)

    stop = threading.Event()
    worker = threading.Thread(target=uploader.run, args=(stop,), daemon=True)
    worker.start()
    view = StatusLoop(screen)
    view.start()

    try:
        for win in Scheduler(mode).windows(_blocks(input_spec)):
            seq = state.next_seq()
            batch = build_batch(cfg, seq, win.start_utc, win.peaks, win.loudness_db, seed)
            outbox.put(batch)
            stamp = datetime.fromtimestamp(win.start_utc, tz=timezone.utc).isoformat(timespec="seconds")
            events.append("window", seq=seq, window_start=batch["window_start"], peaks=int(win.peaks.size),
                          loudness_db=win.loudness_db, input=input_spec)
            screen.note_window(seq, stamp, int(win.peaks.size), win.loudness_db)
    except KeyboardInterrupt:
        pass
    finally:
        view.stop()
        stop.set()
        worker.join(timeout=10)
        client.close()
        print("stopped; unsent batches stay in the outbox:", outbox.count())
    return 0


if __name__ == "__main__":
    sys.exit(run())
