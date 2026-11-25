"""Wait until every uploaded song is fingerprinted (used by scripts/install_server.ps1 after a song import).

    python -m server.tools.wait_fingerprints [--timeout 2400]

Prints the number of songs still waiting every 10 s; exit 0 when none is left, 1 on timeout.
"""
from __future__ import annotations

import argparse
import sys
import time

from server.db import connect


def left(conn) -> int:
    return conn.execute("""SELECT count(*) AS n FROM jobs
                           WHERE kind = 'fingerprint' AND status IN ('queued', 'running')""").fetchone()["n"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeout", type=int, default=2400, help="seconds")
    a = ap.parse_args(argv)
    end = time.monotonic() + a.timeout
    with connect(autocommit=True) as conn:
        while True:
            n = left(conn)
            if n == 0:
                ready = conn.execute("SELECT count(*) AS n FROM songs WHERE status = 'ready' AND n_hashes > 0").fetchone()["n"]
                print(f"all songs fingerprinted ({ready} ready)", flush=True)
                return 0
            if time.monotonic() > end:
                print(f"timeout: {n} songs still waiting", flush=True)
                return 1
            print(f"      {n} songs left", flush=True)
            time.sleep(10)


if __name__ == "__main__":
    sys.exit(main())
