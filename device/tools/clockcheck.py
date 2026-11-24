"""Clock check (A-T08): how far is this laptop's clock from B's server, and from an NTP server?

    python -m device.tools.clockcheck --url http://192.168.1.51:8000
Prints the skew in seconds. The agent already reports skew from B's heartbeat; this is the manual check.
"""
import argparse
import socket
import struct
import time
from datetime import datetime, timezone
from typing import Optional

import httpx

NTP_EPOCH_OFFSET = 2208988800  # seconds between 1900-01-01 and 1970-01-01


def parse_server_time(text: str) -> float:
    """'2026-11-24T05:23:58.434Z' -> epoch seconds."""
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc).timestamp()


def skew_from_health(url: str, timeout: float = 5.0) -> Optional[float]:
    """B's clock minus this laptop's clock, using B's /health server_time. Half the round trip is allowed for."""
    t0 = time.time()
    resp = httpx.get(url.rstrip("/") + "/health", timeout=timeout)
    t1 = time.time()
    server = parse_server_time(resp.json()["server_time"])
    return server - (t0 + t1) / 2


def ntp_offset(server: str = "time.windows.com", timeout: float = 3.0) -> Optional[float]:
    """Local clock minus NTP time (SNTP, one packet). None if the NTP server cannot be reached."""
    packet = b"\x1b" + 47 * b"\0"
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(timeout)
            t0 = time.time()
            s.sendto(packet, (server, 123))
            data, _ = s.recvfrom(48)
            t1 = time.time()
    except OSError:
        return None
    secs, frac = struct.unpack("!II", data[40:48])  # transmit timestamp
    ntp_time = secs - NTP_EPOCH_OFFSET + frac / 2**32
    return (t0 + t1) / 2 - ntp_time


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="clock check (A-T08)")
    p.add_argument("--url", default="http://192.168.1.51:8000")
    args = p.parse_args(argv)
    try:
        s = skew_from_health(args.url)
        print(f"B server clock minus this laptop: {s:+.3f} s")
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        print(f"B server: could not read /health ({type(exc).__name__})")
    n = ntp_offset()
    if n is None:
        print("NTP (time.windows.com): not reachable (no internet, or UDP 123 blocked)")
    else:
        print(f"NTP minus this laptop: {-n:+.3f} s  (positive = this laptop is behind)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
