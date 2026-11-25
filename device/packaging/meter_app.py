"""Fair Play meter, packaged for Windows (FairPlayMeter.exe). Wraps the agent (device.agent) for a bar laptop.

Double-click: no questions. The first start sets the meter up by itself (its own key, a free meter id, the bar and the
SONACAM address built into the exe), asks SONACAM to join and says "Waiting for approval from SONACAM". Once SONACAM
approves it on the operations page, the meter listens in the background and shows a small menu
(status, pause/resume, check connection, meter details, stop).

    FairPlayMeter.exe                 the above
    FairPlayMeter.exe check           list microphones, check SONACAM and the approval
    FairPlayMeter.exe setup [--meter M-xx] [--venue V-..] [--url ..] [--force]   set up by hand (optional)
    FairPlayMeter.exe run [--input file:<path>] [--mode demo|field]              start with other input/mode

Everything lives next to the .exe: device/config (settings), device/secrets (this meter's private key, never shared),
device/state (outbox, logs, approval) and contract/meters (its public key). No sound is stored or sent: only fingerprints.

Approval works with both kinds of SONACAM server: one with the join step (POST /v1/meters/join, shown under
Operations > Waiting for approval) and an older one, where the signed heartbeat tells whether the key is registered
(200 registered, 404 not yet, 401 the id belongs to another key, 403 retired).
"""
import argparse
import glob
import json
import os
import random
import sys
import threading
import time
import tomllib

APP_DIR = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.getcwd()


def data_dir():
    """Where the meter keeps its key, settings and queue: ONE place per computer, so every copy of the exe on this
    computer is the same meter (and cannot ask SONACAM a second time). A meter set up next to an older exe stays there."""
    if glob.glob(os.path.join(APP_DIR, "device", "config", "*.toml")) or not getattr(sys, "frozen", False):
        return APP_DIR
    for base in (os.environ.get("PROGRAMDATA"), os.environ.get("LOCALAPPDATA")):
        if base:
            d = os.path.join(base, "FairPlayMeter")
            try:
                os.makedirs(d, exist_ok=True)
                return d
            except OSError:
                continue
    return APP_DIR


def device_id():
    """A stable, anonymous id for this computer (hash of Windows' MachineGuid), sent with the join request."""
    import hashlib
    raw = ""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography",
                            0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as k:
            raw = winreg.QueryValueEx(k, "MachineGuid")[0]
    except Exception:  # noqa: BLE001 - not Windows, or no access: fall back to the network card's address
        import uuid
        raw = f"node-{uuid.getnode()}"
    return hashlib.sha256(f"fairplay:{raw}".encode()).hexdigest()[:32]


DEFAULT_VENUE = "V-BUEA-CIMFEST"
WAIT_S = 15
OLD_SERVER_WAIT_S = 30          # an older server logs every refused heartbeat: ask less often


def _default_sonacam():
    """The address baked in at build time (build.ps1 -Url writes sonacam_url.txt into the build, never into git)."""
    for d in (getattr(sys, "_MEIPASS", ""), APP_DIR, os.path.dirname(os.path.abspath(__file__))):
        p = os.path.join(d, "sonacam_url.txt")
        if d and os.path.isfile(p):
            with open(p, encoding="utf-8") as fh:
                url = fh.read().strip()
            if url:
                return url
    return "http://192.168.1.51:8000"


DEFAULT_SONACAM = _default_sonacam()


def key_fingerprint(key_b64):
    """Same as the SONACAM operations page shows (server/registry.py), so both sides can compare it."""
    import hashlib
    h = hashlib.sha256(key_b64.encode()).hexdigest()[:16]
    return " ".join(h[i:i + 4] for i in range(0, 16, 4))


# ---------------------------------------------------------------- files next to the exe
def _cfg_path(mid):
    return os.path.join("device", "config", f"{mid}.toml")


def _pub_path(mid):
    return os.path.join("contract", "meters", f"{mid}.pub.json")


def _approved_flag(mid):
    return os.path.join("device", "state", f"{mid}.approved")


def _configs():
    return sorted(glob.glob(os.path.join("device", "config", "*.toml")))


def _load_cfg(path):
    with open(path, "rb") as fh:
        return tomllib.load(fh)


def _pub_key(mid):
    with open(_pub_path(mid), encoding="utf-8") as fh:
        return json.load(fh)["public_key_b64"]


def new_meter_id():
    """A free-looking id; if SONACAM already has it, the meter picks another one by itself."""
    return f"M-{random.randint(2000, 9999)}"


def setup(meter=None, venue=None, url=None, force=False, quiet=False):
    """Make this meter's key and config. No questions: anything not given gets its default."""
    import tomli_w
    from device.tools.provision import provision
    meter = meter or new_meter_id()
    venue = venue or DEFAULT_VENUE
    url = (url or DEFAULT_SONACAM).rstrip("/")
    pub = provision(meter, venue, input_src="mic", mode="demo", force=force)
    cfg = _load_cfg(_cfg_path(meter))
    cfg["sonacam_url"] = url
    with open(_cfg_path(meter), "wb") as fh:
        tomli_w.dump(cfg, fh)
    if not quiet:
        print(f"Meter {meter} set up for {venue}, sending to {url}. Key fingerprint {key_fingerprint(pub['public_key_b64'])}")
    return cfg


def _forget(mid):
    """Remove an old identity: settings, keys, approval and its queue (a retired meter's reports are refused anyway)."""
    paths = [_cfg_path(mid), _pub_path(mid), os.path.join("device", "secrets", f"{mid}.seed"), _approved_flag(mid)]
    paths += glob.glob(os.path.join("device", "state", f"{mid}_*")) + glob.glob(os.path.join("device", "state", f"{mid}.*"))
    for p in paths:
        try:
            if os.path.exists(p):
                os.remove(p)
        except OSError:
            pass                                     # a file still open: harmless, the new meter has its own names


def _renumber(cfg):
    """The id belongs to another meter: same bar and address, new id and new key."""
    old = cfg["meter_id"]
    new = setup(None, cfg["venue_id"], cfg["sonacam_url"], quiet=True)
    _forget(old)
    return new


# ---------------------------------------------------------------- asking SONACAM
def ask_to_join(cfg):
    """Send this meter's public key, signed with its own private key, to SONACAM (POST /v1/meters/join).
    Returns (status, detail): approved | pending | rejected | retired | taken | old_server | unreachable | error."""
    import socket
    import httpx
    from fairplay_core.signing import sign_dict
    from device.tools.provision import load_seed
    mid = cfg["meter_id"]
    with open(_pub_path(mid), encoding="utf-8") as fh:
        pub = json.load(fh)
    body = {k: pub[k] for k in ("meter_id", "venue_id", "public_key_b64", "created_at") if k in pub}
    body["computer"] = socket.gethostname()[:80]
    body["device_id"] = device_id()
    body["sig"] = sign_dict(load_seed(mid), body)
    try:
        r = httpx.post(cfg["sonacam_url"].rstrip("/") + "/v1/meters/join", json=body, timeout=30)
    except Exception as e:  # noqa: BLE001 - any network error: report it plainly
        return "unreachable", type(e).__name__
    if r.status_code in (404, 405) and "status" not in r.text:
        return "old_server", "this SONACAM server has no join step yet"
    try:
        j = r.json()
    except ValueError:
        return "error", f"HTTP {r.status_code}"
    if j.get("error") == "meter_id_taken":
        return "taken", j.get("detail", "")
    if j.get("error") in ("device_already_waiting", "device_has_meter"):
        return "computer_busy", j.get("detail", "")
    return j.get("status") or "error", j.get("detail") or f"HTTP {r.status_code}"


def heartbeat_status(cfg):
    """Works with every SONACAM server: a signed heartbeat says whether this key is registered."""
    import httpx
    from device.agent.batcher import sign_fields
    from device.agent.uploader import _utc_now_iso
    from device.tools.provision import load_seed
    hb = {"meter_id": cfg["meter_id"], "venue_id": cfg["venue_id"], "sent_at": _utc_now_iso(), "queued": 0,
          "fw": cfg.get("fw", "agent-0.1.0")}
    hb["sig"] = sign_fields(load_seed(cfg["meter_id"]), hb)
    try:
        r = httpx.post(cfg["sonacam_url"].rstrip("/") + "/v1/heartbeat", json=hb, timeout=30)
    except Exception as e:  # noqa: BLE001
        return "unreachable", type(e).__name__
    return {200: ("approved", ""), 404: ("pending", "not registered yet"), 401: ("taken", "id belongs to another key"),
            403: ("retired", "retired by SONACAM")}.get(r.status_code, ("error", f"HTTP {r.status_code}"))


def approval(cfg):
    """(status, detail, old_server). The join step first; an older server is asked through the heartbeat."""
    status, detail = ask_to_join(cfg)
    if status in ("approved", "pending", "rejected", "retired", "taken", "unreachable", "computer_busy"):
        return status, detail, False
    status, detail = heartbeat_status(cfg)
    return status, detail, True


def wait_for_approval(cfg):
    """Wait until SONACAM approves this meter. Returns the (maybe renumbered) config, or None to stop."""
    if os.path.exists(_approved_flag(cfg["meter_id"])):
        status, _, _ = approval(cfg)
        if status not in ("retired", "rejected", "taken"):
            return cfg                               # still approved, or no internet: start (reports wait)
        # SONACAM retired this meter (or its id now belongs to another key): this laptop asks again as a NEW meter
        print(f"\nSONACAM has {'retired' if status != 'taken' else 'given away'} meter {cfg['meter_id']}. "
              "This laptop now asks to join again as a new meter.")
        cfg = _renumber(cfg)
    shown = old_note = offline_note = busy_note = False
    while True:
        status, detail, old = approval(cfg)
        if status == "approved":
            os.makedirs(os.path.dirname(_approved_flag(cfg["meter_id"])), exist_ok=True)
            with open(_approved_flag(cfg["meter_id"]), "w", encoding="utf-8") as fh:
                fh.write(time.strftime("%Y-%m-%d %H:%M"))
            line = "=" * 64
            print(f"\a\n\n  {line}\n   APPROVED by SONACAM. Meter {cfg['meter_id']} now counts the music played here.\n  {line}")
            return cfg
        if status == "computer_busy":                # this computer already asked (or already is a meter)
            if not busy_note:
                print(f"\n  {detail}.\n  Waiting: SONACAM can reject or retire the other one.\n")
                busy_note = True
            print(".", end="", flush=True)
            time.sleep(OLD_SERVER_WAIT_S)
            continue
        if status == "taken":                        # someone else has this id: take another one, silently
            cfg = _renumber(cfg)
            shown = False
            continue
        if status in ("rejected", "retired"):
            print(f"\n\nSONACAM has {status} this meter ({cfg['meter_id']}). It will not listen.")
            return None
        if not shown:
            print("\nWaiting for approval from SONACAM...\n")
            print(f"  Meter            {cfg['meter_id']}")
            print(f"  Bar              {cfg['venue_id']}")
            print(f"  Key fingerprint  {key_fingerprint(_pub_key(cfg['meter_id']))}")
            print("\n  SONACAM approves it on the operations page (Meters). The fingerprint there must match.")
            print("  This window can stay open; listening starts by itself once approved.\n")
            shown = True
        if old and not old_note:
            print(f"  (SONACAM's server is not updated yet: register {os.path.abspath(_pub_path(cfg['meter_id']))}")
            print("   under Operations > Register a meter.)\n")
            old_note = True
        if status == "unreachable" and not offline_note:
            print(f"  (Cannot reach SONACAM right now: {detail}. Still trying.)\n")
            offline_note = True
        print(".", end="", flush=True)
        time.sleep(OLD_SERVER_WAIT_S if old else WAIT_S)


# ---------------------------------------------------------------- listening in the background
class Listener:
    """Runs the agent pipeline in a background thread; pause, resume and stop from the menu."""

    def __init__(self, cfg, input_spec="mic", mode="demo"):
        self.cfg, self.input_spec, self.mode = cfg, input_spec, mode
        self.paused = threading.Event()
        self.stopping = threading.Event()
        self.screen = None
        self.error = None
        self.started_at = time.time()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _blocks(self):
        from device.agent.__main__ import _blocks
        gap = False
        for block in _blocks(self.input_spec):
            if self.stopping.is_set():
                return
            if self.paused.is_set():
                gap = True                       # sound while paused is dropped, never measured
                continue
            if gap:
                gap = False
                yield None                       # a gap: the scheduler starts fresh windows after a pause
            yield block

    def _ready(self, screen):
        self.screen = screen

    def _run(self):
        from device.agent.__main__ import run_pipeline
        try:
            run_pipeline(self.cfg, self.mode, self._blocks(), self.input_spec, show_screen=False,
                         drain_timeout_s=10.0, on_ready=self._ready)
        except BaseException as e:  # noqa: BLE001 - show it in the menu instead of dying silently
            self.error = f"{type(e).__name__}: {e}"

    def start(self):
        self.thread.start()
        return self

    def stop(self):
        self.stopping.set()
        self.thread.join(timeout=20)

    def status_lines(self):
        s, up = self.screen, (self.screen.uploader if self.screen else None)
        if self.error:
            state = f"NOT LISTENING ({self.error})"
        elif not self.thread.is_alive():
            state = "stopped"
        elif self.paused.is_set():
            state = "paused"
        else:
            state = "listening"
        flag = _approved_flag(self.cfg["meter_id"])
        since = ""
        if os.path.exists(flag):
            with open(flag, encoding="utf-8") as fh:
                since = fh.read().strip()
        lines = [f"Approved         yes, by SONACAM{f' ({since})' if since else ''}",
                 f"State            {state}",
                 f"Running for      {int((time.time() - self.started_at) // 60)} min"]
        if s is not None:
            loud = f"{s.last_window[2]:.0f} dB" if s.last_window else "no sound measured yet"
            lines += [f"Sound level      {loud}",
                      f"10-s samples     {s.captured} made, {up.acked} sent to SONACAM",
                      f"Waiting to send  {s.outbox.count()}" + (f" ({len(up.parked)} refused, kept)" if up.parked else ""),
                      f"Network          {up.network_state}",
                      f"Last problem     {up.last_error or 'none'}"]
        return lines


def _check_connection(cfg):
    import httpx
    t = time.monotonic()
    try:
        r = httpx.get(cfg["sonacam_url"].rstrip("/") + "/health", timeout=30)
        took = time.monotonic() - t
        print(f"  SONACAM answers (HTTP {r.status_code}) in {took:.1f} s.")
    except Exception as e:  # noqa: BLE001
        print(f"  SONACAM does not answer ({type(e).__name__}). Samples wait on this laptop and are sent later.")
        return
    status, detail, _ = approval(cfg)
    print(f"  Approval: {status}" + (f" ({detail})" if status not in ("approved",) and detail else ""))


def _details(cfg):
    import socket
    print(f"  Meter            {cfg['meter_id']}")
    print(f"  Bar              {cfg['venue_id']}")
    print(f"  SONACAM          {cfg['sonacam_url']}")
    print(f"  Key fingerprint  {key_fingerprint(_pub_key(cfg['meter_id']))}")
    print(f"  Computer         {socket.gethostname()}")
    print(f"  Kept in          {os.getcwd()}")


MENU = """
  1  Status
  2  {pause}
  3  Check the connection to SONACAM
  4  Meter details
  5  Stop and close
"""


def menu(cfg, listener):
    print(f"\nListening in the background. Meter {cfg['meter_id']} at {cfg['venue_id']}.")
    print("No sound is recorded or sent: only fingerprints. You can minimise this window.")
    while True:
        print(MENU.format(pause="Resume listening" if listener.paused.is_set() else "Pause listening"))
        try:
            choice = input("Choose 1-5: ").strip()
        except EOFError:                              # no keyboard (started by a script): just keep listening
            listener.thread.join()
            return
        except KeyboardInterrupt:
            choice = "5"
        print()
        if choice == "1":
            print("\n".join("  " + x for x in listener.status_lines()))
        elif choice == "2":
            if listener.paused.is_set():
                listener.paused.clear()
                print("  Listening again.")
            else:
                listener.paused.set()
                print("  Paused: nothing is heard until you resume.")
        elif choice == "3":
            _check_connection(cfg)
        elif choice == "4":
            _details(cfg)
        elif choice == "5":
            print("  Stopping...")
            listener.stop()
            print("  Stopped. Anything not sent yet is kept and goes out at the next start.")
            return
        else:
            print("  Type a number from 1 to 5.")


def start(input_spec=None, mode=None):
    cfgs = _configs()
    if cfgs:
        cfg = _load_cfg(cfgs[0])
        print(f"Fair Play meter {cfg['meter_id']}.")
    else:
        print("Fair Play meter: first start, setting up this laptop...")
        cfg = setup(quiet=True)
    cfg = wait_for_approval(cfg)
    if cfg is None:
        return 1
    listener = Listener(cfg, input_spec or cfg.get("input", "mic"), mode or cfg.get("mode", "demo")).start()
    menu(cfg, listener)
    return 0


def check():
    import sounddevice as sd
    print("Microphones:")
    default_in = sd.default.device[0] if sd.default.device else None
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0:
            print(f"  {'*' if i == default_in else ' '} {i}: {d['name']}")
    for path in _configs():
        cfg = _load_cfg(path)
        print(f"\n{cfg['meter_id']} at {cfg['venue_id']}, SONACAM {cfg.get('sonacam_url', '')}:")
        if not os.path.exists(os.path.join("device", "secrets", f"{cfg['meter_id']}.seed")):
            print("  NO KEY: delete the device and contract folders and start again")
            continue
        _check_connection(cfg)
        print(f"  Key fingerprint {key_fingerprint(_pub_key(cfg['meter_id']))}")
    if not _configs():
        print("\nNot set up yet: double-click FairPlayMeter.exe")


def main(argv=None):
    os.chdir(data_dir())
    p = argparse.ArgumentParser(prog="FairPlayMeter")
    sub = p.add_subparsers(dest="cmd")
    s = sub.add_parser("setup", help="set up this meter by hand (normally automatic)")
    s.add_argument("--meter"); s.add_argument("--venue"); s.add_argument("--url")
    s.add_argument("--force", action="store_true", help="replace an existing key")
    sub.add_parser("check", help="list microphones, check SONACAM and the approval")
    r = sub.add_parser("run", help="start (same as double-click), optionally with another input or mode")
    r.add_argument("--input"); r.add_argument("--mode", choices=["demo", "field"])
    args = p.parse_args(argv)
    if args.cmd == "setup":
        setup(args.meter, args.venue, args.url, force=args.force)
        return 0
    if args.cmd == "check":
        check()
        return 0
    if args.cmd == "run":
        return start(args.input, args.mode)
    return start()


if __name__ == "__main__":
    code = main()
    if getattr(sys, "frozen", False) and len(sys.argv) == 1:
        try:
            input("\nPress Enter to close.")
        except (EOFError, KeyboardInterrupt):
            pass
    sys.exit(code)
