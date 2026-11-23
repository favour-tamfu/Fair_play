# Fair Play

**Music meters that tell SONACAM whose songs were actually played, so artists are paid by real plays, not a flat 27,000 FCFA.**

CIMFEST Hackathon 2026 — "Africa's creative economy" — Buea, Cameroon.

> Status: under construction during the hackathon. Sections marked *(TODO)* get filled as the build progresses.

## What it is
- **Laptop A — the meter:** listens to a bar's music, extracts an audio signature (spectral peaks, never audio), signs it and sends it.
- **Laptop B — SONACAM server:** fingerprints the catalogue, matches what meters heard, logs plays in a tamper-evident ledger, applies fair-play rules, estimates national shares and splits the royalty pot.

## Quick start (Windows) *(TODO — B-T17)*
```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -U pip
pip install -e core -r requirements-dev.txt
```

### Server stack (Laptop B, Docker Desktop running)
```powershell
Copy-Item .env.example .env        # first time only; then set a real POSTGRES_PASSWORD (same value in DATABASE_URL)
docker compose up -d --build       # db, api, worker_fp, worker_match, worker_play, scheduler
docker compose ps                  # api + db should say (healthy)
curl http://localhost:8000/health  # {"ok":true,"db":true,...}
.\scripts\test_b.ps1               # B's tests (DB tests use a separate <db>_test database)
```
Let the meter (Laptop A) reach port 8000 on the hotspot: run `scripts\firewall_b.ps1` once in an **admin** PowerShell.

## Architecture *(TODO)*
See `docs/00_PROJECT_BRIEF.md §4`.

## Server (Laptop B) *(TODO — owner B)*

## Device (Laptop A) *(TODO — owner A)*

## Web *(TODO — owner A)*

## How the fair-play rules work *(TODO — owner B)*

## Accuracy (measured) *(TODO — owner A)*

## Limits *(TODO)*

## Declarations
All code in this repository was written during the hackathon (Mon 23 Nov – Wed 25 Nov 2026). **Built with Claude Code** (Anthropic), declared as an AI coding tool.

| Library / asset | Version | Licence | Purpose | Added by |
|---|---|---|---|---|
| numpy | 2.1.3 | BSD-3-Clause | arrays, signal maths | B (core) |
| scipy | 1.14.1 | BSD-3-Clause | STFT window, filters, resampling | B (core) |
| PyNaCl | 1.5.0 | Apache-2.0 | Ed25519 signatures | B (core) |
| pydantic | 2.9.2 | MIT | batch schema validation | B (core) |
| pytest | 8.3.3 | MIT | tests | B |
| jsonschema | 4.23.0 | MIT | contract schema validation | B |
| FastAPI | 0.115.5 | MIT | server API | B |
| Uvicorn | 0.32.1 | BSD-3-Clause | ASGI web server | B |
| psycopg | 3.2.3 | LGPL-3.0 | PostgreSQL driver | B |
| python-multipart | 0.0.17 | Apache-2.0 | song upload forms | B |
| pandas | 2.2.3 | BSD-3-Clause | stats tables | B |
| sse-starlette | 2.1.3 | BSD-3-Clause | live feed (Server-Sent Events) | B |
| httpx | 0.27.2 | BSD-3-Clause | test client | B |
| PostgreSQL | 16 (Docker image) | PostgreSQL Licence | database, fingerprint index, job queue | B |
| Python | 3.11-slim (Docker image) | PSF | server runtime | B |
| FFmpeg | Debian package in image | LGPL/GPL | decode uploaded songs | B |
