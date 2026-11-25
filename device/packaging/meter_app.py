"""Fair Play meter, packaged for Windows (FairPlayMeter.exe). Wraps the agent (device.agent) for a bar laptop.

    FairPlayMeter.exe                 first run: set up this meter; afterwards: start listening
    FairPlayMeter.exe setup           set up (or re-key with --force) this meter
    FairPlayMeter.exe check           list microphones and check that SONACAM answers
    FairPlayMeter.exe run [--input file:<path>] [--mode demo|field]

Everything lives next to the .exe: device/config (settings), device/secrets (this meter's private key, never shared),
device/state (outbox and logs) and contract/meters (the public key to register on the SONACAM admin page).
No sound is stored or sent: only fingerprints.
"""
import argparse
import glob
import json
import os
import sys
import time
import tomllib

APP_DIR = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.getcwd()
DEFAULT_VENUE = "V-BUEA-CIMFEST"
WAIT_S = 15


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


def _load_cfg(path):
    with open(path, "rb") as fh:
        return tomllib.load(fh)


def ask_to_join(cfg):
    """Send this meter's public key, signed with its own private key, to SONACAM (POST /v1/meters/join).
    Returns (status, detail): approved | pending | rejected | retired | taken | old_server | unreachable | error."""
    import socket
    import httpx
    from fairplay_core.signing import sign_dict
    from device.tools.provision import load_seed
    mid = cfg["meter_id"]
    with open(os.path.join("contract", "meters", f"{mid}.pub.json"), encoding="utf-8") as fh:
        pub = json.load(fh)
    body = {k: pub[k] for k in ("meter_id", "venue_id", "public_key_b64", "created_at") if k in pub}
    body["computer"] = socket.gethostname()[:80]
    body["sig"] = sign_dict(load_seed(mid), body)
    try:
        r = httpx.post(cfg["sonacam_url"].rstrip("/") + "/v1/meters/join", json=body, timeout=30)
    except Exception as e:  # noqa: BLE001 - any network error: report it plainly
        return "unreachable", type(e).__name__
    if r.status_code in (404, 405) and "status" not in r.text:
        return "old_server", "this SONACAM server has no join step: register the key on the admin page"
    try:
        j = r.json()
    except ValueError:
        return "error", f"HTTP {r.status_code}"
    if j.get("error") == "meter_id_taken":
        return "taken", j.get("detail", "")
    return j.get("status") or "error", j.get("detail") or f"HTTP {r.status_code}"


def wait_for_approval(cfg):
    """Ask to join and wait until SONACAM approves. True = start listening, False = stop."""
    fp = key_fingerprint(_pub_key(cfg["meter_id"]))
    shown = False
    while True:
        status, detail = ask_to_join(cfg)
        if status == "approved":
            if shown:
                print("\nApproved by SONACAM. Starting to listen.")
            return True
        if status == "pending":
            if not shown:
                print(f"\nMeter {cfg['meter_id']} at {cfg['venue_id']} has asked SONACAM to join.")
                print(f"  Key fingerprint: {fp}")
                print("  SONACAM approves it on the operations page (Meters > Waiting for approval);")
                print("  check that the fingerprint there is the same as this one.")
                print(f"Waiting for approval (checking every {WAIT_S} s; Ctrl+C to stop)", end="", flush=True)
                shown = True
            else:
                print(".", end="", flush=True)
            time.sleep(WAIT_S)
            continue
        if status in ("rejected", "retired"):
            print(f"\nSONACAM has {status} meter {cfg['meter_id']}. It will not listen. Contact SONACAM.")
            return False
        if status == "taken":
            print(f"\n{detail}\nSet this meter up again with another id: FairPlayMeter.exe setup --force")
            return False
        if status == "old_server":
            print(f"\nNote: {detail}. Starting anyway.")
            return True
        if shown:                                   # already waiting: a dropped connection just means "ask again"
            print("?", end="", flush=True)
            time.sleep(WAIT_S)
            continue
        print(f"\nSONACAM did not answer ({detail}). Starting anyway: reports wait on this laptop until it answers.")
        return True


def _pub_key(meter_id):
    with open(os.path.join("contract", "meters", f"{meter_id}.pub.json"), encoding="utf-8") as fh:
        return json.load(fh)["public_key_b64"]


def _configs():
    return sorted(glob.glob(os.path.join("device", "config", "*.toml")))


def _ask(prompt, default=""):
    try:
        v = input(f"{prompt}{f' [{default}]' if default else ''}: ")
        # ids and addresses are plain ASCII; this also drops a byte-order mark some consoles put before piped input
        v = "".join(ch for ch in v if 32 <= ord(ch) < 127).strip()
    except EOFError:
        v = ""
    return v or default


def setup(force=False, meter=None, venue=None, url=None):
    import tomli_w
    from device.tools.provision import provision
    print("Fair Play meter setup. This makes a private key for this meter; keep this folder private.\n")
    meter = meter or _ask("Meter id (from SONACAM, e.g. M-21)")
    venue = venue or _ask("Bar (venue) id", DEFAULT_VENUE)
    url = url or _ask("SONACAM address", DEFAULT_SONACAM)
    if not meter or not venue:
        raise SystemExit("A meter id and a venue id are needed.")
    pub = provision(meter, venue, input_src="mic", mode="demo", force=force)
    path = os.path.join("device", "config", f"{meter}.toml")
    with open(path, "rb") as fh:
        cfg = tomllib.load(fh)
    cfg["sonacam_url"] = url
    with open(path, "wb") as fh:
        tomli_w.dump(cfg, fh)
    print(f"\nMeter {meter} set up for {venue}, sending to {url}.")
    print(f"Key fingerprint: {key_fingerprint(pub['public_key_b64'])}")
    status, detail = ask_to_join(cfg)
    if status == "pending":
        print("Asked SONACAM to join: it appears on the operations page under Meters > Waiting for approval.")
    elif status == "approved":
        print("SONACAM already knows this meter.")
    elif status == "taken":
        print(detail)
    else:
        pub_path = os.path.abspath(os.path.join("contract", "meters", f"{meter}.pub.json"))
        print(f"Could not ask SONACAM to join yet ({status}: {detail}); it is asked again when the meter starts.")
        print(f"(Manual way: register {pub_path} on the operations page.)")
    print()
    return path


def check():
    import httpx
    import sounddevice as sd
    print("Microphones:")
    default_in = sd.default.device[0] if sd.default.device else None
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0:
            print(f"  {'*' if i == default_in else ' '} {i}: {d['name']}")
    for path in _configs():
        with open(path, "rb") as fh:
            cfg = tomllib.load(fh)
        url = cfg.get("sonacam_url", "")
        try:
            r = httpx.get(url.rstrip("/") + "/api/v1/overview", timeout=5)
            ok = f"answers (HTTP {r.status_code})"
        except Exception as e:  # noqa: BLE001 - report any network error plainly
            ok = f"not reachable ({type(e).__name__})"
        has_key = os.path.exists(os.path.join("device", "secrets", f"{cfg['meter_id']}.seed"))
        key = "key present" if has_key else "NO KEY: run setup"
        print(f"\n{cfg['meter_id']} at {cfg['venue_id']}: SONACAM {url} {ok}; {key}")
        if has_key:
            status, detail = ask_to_join(cfg)
            print(f"  key fingerprint {key_fingerprint(_pub_key(cfg['meter_id']))}; SONACAM approval: {status}"
                  + ("" if status in ("approved", "pending") else f" ({detail})"))
    if not _configs():
        print("\nNo meter set up yet: run FairPlayMeter.exe setup")


def run(extra):
    from device.agent.__main__ import run as agent_run
    cfgs = _configs()
    if not cfgs:
        cfgs = [setup()]
    cfg = cfgs[0]
    if len(cfgs) > 1:
        print("Meters set up here:", ", ".join(os.path.basename(c)[:-5] for c in cfgs))
        pick = _ask("Which meter", os.path.basename(cfgs[0])[:-5])
        cfg = os.path.join("device", "config", f"{pick}.toml")
    if not wait_for_approval(_load_cfg(cfg)):
        return 1
    return agent_run(["run", "--config", cfg, *extra])


def main(argv=None):
    os.chdir(APP_DIR)
    p = argparse.ArgumentParser(prog="FairPlayMeter")
    sub = p.add_subparsers(dest="cmd")
    s = sub.add_parser("setup", help="set up this meter (makes its key)")
    s.add_argument("--meter"); s.add_argument("--venue"); s.add_argument("--url")
    s.add_argument("--force", action="store_true", help="replace an existing key")
    sub.add_parser("check", help="list microphones, check SONACAM")
    r = sub.add_parser("run", help="start listening")
    r.add_argument("--input"); r.add_argument("--mode", choices=["demo", "field"])
    args = p.parse_args(argv)
    if args.cmd == "setup":
        setup(args.force, args.meter, args.venue, args.url)
        return 0
    if args.cmd == "check":
        check()
        return 0
    extra = []
    if args.cmd == "run":
        if args.input: extra += ["--input", args.input]
        if args.mode: extra += ["--mode", args.mode]
    return run(extra)


if __name__ == "__main__":
    code = main()
    if getattr(sys, "frozen", False) and len(sys.argv) == 1:
        input("\nPress Enter to close.")
    sys.exit(code)
