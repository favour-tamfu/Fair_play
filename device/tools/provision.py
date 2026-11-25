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


# The private seed is kept encrypted with Windows' data protection (DPAPI), tied to this computer: a copied .seed file
# is useless on another machine. File content: "dpapi:<base64>" (Windows) or the hex seed (elsewhere, and older files).
DPAPI_PREFIX = "dpapi:"


def _dpapi(data: bytes, decrypt: bool) -> bytes:
    import ctypes
    from ctypes import wintypes

    class BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    buf = ctypes.create_string_buffer(data, len(data))
    inp = BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    out = BLOB()
    UI_FORBIDDEN, LOCAL_MACHINE = 0x1, 0x4        # machine scope: any account on THIS computer, no other computer
    fn = ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    flags = UI_FORBIDDEN if decrypt else UI_FORBIDDEN | LOCAL_MACHINE
    if not fn(ctypes.byref(inp), None, None, None, None, flags, ctypes.byref(out)):
        raise OSError(f"Windows data protection failed (error {ctypes.GetLastError()})")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


def _write_seed(meter_id: str, seed: bytes) -> None:
    text = binascii.hexlify(seed).decode("ascii")
    if os.name == "nt":
        text = DPAPI_PREFIX + base64.b64encode(_dpapi(seed, decrypt=False)).decode("ascii")
    with open(seed_path(meter_id), "w", encoding="ascii") as fh:
        fh.write(text + "\n")


def load_seed(meter_id: str) -> bytes:
    with open(seed_path(meter_id), "r", encoding="ascii") as fh:
        text = fh.read().strip()
    if text.startswith(DPAPI_PREFIX):
        return _dpapi(base64.b64decode(text[len(DPAPI_PREFIX):]), decrypt=True)
    seed = binascii.unhexlify(text)
    if os.name == "nt":                            # an older plain key: encrypt it in place from now on
        try:
            _write_seed(meter_id, seed)
        except OSError:
            pass
    return seed


def provision(meter_id: str, venue_id: str, cell_id: str = DEFAULT_CELL, input_src: str = "mic", mode: str = "demo", force: bool = False) -> dict:
    if os.path.exists(seed_path(meter_id)) and not force:
        raise SystemExit(f"{meter_id} already provisioned (seed exists). Use --force to replace the key.")
    os.makedirs(SECRETS_DIR, exist_ok=True)
    os.makedirs(CONFIG_DIR, exist_ok=True)
    os.makedirs(METERS_DIR, exist_ok=True)

    key = nacl.signing.SigningKey.generate()
    _write_seed(meter_id, bytes(key))

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
