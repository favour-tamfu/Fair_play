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
import tomllib

APP_DIR = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.getcwd()
DEFAULT_SONACAM = "http://192.168.1.51:8000"


def _configs():
    return sorted(glob.glob(os.path.join("device", "config", "*.toml")))


def _ask(prompt, default=""):
    try:
        v = input(f"{prompt}{f' [{default}]' if default else ''}: ").strip()
    except EOFError:
        v = ""
    return v or default


def setup(force=False, meter=None, venue=None, url=None):
    import tomli_w
    from device.tools.provision import provision
    print("Fair Play meter setup. This makes a private key for this meter; keep this folder private.\n")
    meter = meter or _ask("Meter id (from SONACAM, e.g. M-21)")
    venue = venue or _ask("Venue id (from SONACAM, e.g. V-DLA-AKWA01)")
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
    pub_path = os.path.abspath(os.path.join("contract", "meters", f"{meter}.pub.json"))
    print(f"\nMeter {meter} set up for {venue}, sending to {url}.")
    print("Register this public key on the SONACAM admin page (Register meter key) before the first upload:")
    print(f"  {pub['public_key_b64']}")
    print(f"  (also saved in {pub_path})\n")
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
        key = "key present" if os.path.exists(os.path.join("device", "secrets", f"{cfg['meter_id']}.seed")) else "NO KEY: run setup"
        print(f"\n{cfg['meter_id']} at {cfg['venue_id']}: SONACAM {url} {ok}; {key}")
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
