"""Key and config provisioning for a meter (A-T03).

    python -m device.tools.provision --meter M-07 --venue V-BUEA-CIMFEST [--cell 624-01-0412-01733]
    python -m device.tools.provision --all      # M-07 (live) plus virtual M-11..M-13

Writes:
  device/secrets/<meter>.seed         private seed, hex (gitignored, never commit)
  contract/meters/<meter>.pub.json    public key (contract §3.3, committed)
  device/config/<meter>.toml          meter config (committed)
"""
import argparse
import binascii
import base64
import json
import os
from datetime import datetime, timezone

import nacl.signing
import tomli_w

SECRETS_DIR = os.path.join("device", "secrets")
CONFIG_DIR = os.path.join("device", "config")
METERS_DIR = os.path.join("contract", "meters")
DEFAULT_CELL = "624-01-0412-01733"
DEFAULT_URL = "http://192.168.137.1:8000"

# Live meter first, then virtual meters with the venues from the mock month (A-T10).
ALL_METERS = [
    ("M-07", "V-BUEA-CIMFEST", "mic"),
    ("M-11", "V-DLA-AKWA01", "file:data/playlists/akwa.m3u"),
    ("M-12", "V-YDE-BASTO1", "file:data/playlists/bastos.m3u"),
    ("M-13", "V-BUEA-MOLYK1", "file:data/playlists/molyko.m3u"),
]


def seed_path(meter_id: str) -> str:
    return os.path.join(SECRETS_DIR, f"{meter_id}.seed")


def load_seed(meter_id: str) -> bytes:
    with open(seed_path(meter_id), "r", encoding="ascii") as fh:
        return binascii.unhexlify(fh.read().strip())


def provision(meter_id: str, venue_id: str, cell_id: str = DEFAULT_CELL, input_src: str = "mic", mode: str = "demo", force: bool = False) -> dict:
    if os.path.exists(seed_path(meter_id)) and not force:
        raise SystemExit(f"{meter_id} already provisioned (seed exists). Use --force to replace the key.")
    os.makedirs(SECRETS_DIR, exist_ok=True)
    os.makedirs(CONFIG_DIR, exist_ok=True)
    os.makedirs(METERS_DIR, exist_ok=True)

    key = nacl.signing.SigningKey.generate()
    with open(seed_path(meter_id), "w", encoding="ascii") as fh:
        fh.write(binascii.hexlify(bytes(key)).decode("ascii") + "\n")

    pub = {
        "meter_id": meter_id,
        "venue_id": venue_id,
        "public_key_b64": base64.b64encode(bytes(key.verify_key)).decode("ascii"),
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    with open(os.path.join(METERS_DIR, f"{meter_id}.pub.json"), "w", encoding="utf-8") as fh:
        json.dump(pub, fh, indent=2)
        fh.write("\n")

    cfg = {
        "meter_id": meter_id,
        "venue_id": venue_id,
        "cell_id": cell_id,
        "fw": "agent-0.1.0",
        "mode": mode,
        "sonacam_url": DEFAULT_URL,
        "input": input_src,
        "heartbeat_s": 60,
    }
    with open(os.path.join(CONFIG_DIR, f"{meter_id}.toml"), "wb") as fh:
        tomli_w.dump(cfg, fh)
    return pub


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Provision meter keys and config")
    p.add_argument("--meter")
    p.add_argument("--venue")
    p.add_argument("--cell", default=DEFAULT_CELL)
    p.add_argument("--input", default="mic")
    p.add_argument("--force", action="store_true")
    p.add_argument("--all", action="store_true", help="provision M-07 and virtual M-11..M-13")
    args = p.parse_args(argv)
    if args.all:
        for meter, venue, src in ALL_METERS:
            pub = provision(meter, venue, args.cell, src, force=args.force)
            print(f"provisioned {meter} at {venue} (pub {pub['public_key_b64'][:12]}...)")
        return 0
    if not (args.meter and args.venue):
        p.error("--meter and --venue are required (or use --all)")
    pub = provision(args.meter, args.venue, args.cell, args.input, force=args.force)
    print(f"provisioned {args.meter} at {args.venue} (pub {pub['public_key_b64'][:12]}...)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
