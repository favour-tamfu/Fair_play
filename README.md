# Fair Play

**A small "listening box" in every bar tells SONACAM which Cameroonian songs were really played, so each artist's share of the royalties follows real plays, not a flat 27,000 FCFA for everyone.**

CIMFEST Hackathon 2026 · "Africa's creative economy" · Buea, Cameroon

---

## Contents
1. [Fair Play in one minute](#1-fair-play-in-one-minute)
2. [The real product](#2-the-real-product)
3. [How it works](#3-how-it-works)
4. [Quick start (Windows)](#4-quick-start-windows)
5. [The SONACAM server](#5-the-sonacam-server)
6. [How the fair-play rules work](#6-how-the-fair-play-rules-work)
7. [Trust: the tamper-proof play log](#7-trust-the-tamper-proof-play-log)
8. [Measured during the hackathon](#8-measured-during-the-hackathon)
9. [Device (the meter software)](#9-device-the-meter-software)
10. [Web pages](#10-web-pages)
11. [Limits (what this prototype does not do)](#11-limits-what-this-prototype-does-not-do)
12. [Declarations](#12-declarations)

---

## 1. Fair Play in one minute

| Today | With Fair Play |
|---|---|
| SONACAM collects money from bars but cannot see what was played, so it pays every artist the same flat advance. | A meter in each bar recognises the songs it hears (like a music-recognition app) and reports them. |
| Popular artists are underpaid, and nobody can check the split. | Each artist's share = how much their songs were really played, after fair-play rules against abuse. |
| Records can be changed quietly. | Every play is written into a tamper-proof log; any change is detected in about a second. |

**Privacy:** the meter never records or sends sound. It sends only a "fingerprint" of the music (a list of the loudest notes over time), which cannot be turned back into audio or speech.

---

## 2. The real product

Fair Play has four pieces. In real life they look like this:

| Piece | In the real world | Who uses it |
|---|---|---|
| **The meter** | A small sealed box on the bar wall, about the size of a phone charger: a low-cost chip (RISC-V microcontroller), a small microphone and a 4G modem. Parts cost about $5–8. It plugs into the mains and needs no Wi-Fi from the bar. | Installed by SONACAM in every bar it licenses |
| **The SONACAM server** | SONACAM's computer system (in a data centre or the cloud). It receives the meters' reports, recognises the songs, keeps the tamper-proof log and computes each artist's share. | SONACAM |
| **The SONACAM dashboard** | A web page: meters on a map, songs heard live, each artist's share, items to review, the log's integrity. | SONACAM staff |
| **The artist page and upload portal** | Web pages that work on a phone: artists or labels upload their songs and owners; each artist sees where and how often their songs were played and their share. | Artists, labels |

**What the meter does, all day, by itself:**
1. Listens for 10 seconds every minute.
2. Turns those 10 seconds into a fingerprint (the loudest notes over time, never the sound itself).
3. Seals the fingerprint with its own secret key, so nobody can fake or change it on the way.
4. Sends it over 4G (a few kilobytes); if the network is down, it keeps everything and sends it later, in order.
5. Reports which phone tower it is near, so a meter moved to another place is noticed.

### During the hackathon
We could not get the electronics in time, so two laptops play the roles:
- **Laptop A plays the meter.** It runs exactly the computation the box would run (microphone → fingerprint → seal → send), plus "virtual meters" fed with recorded audio for testing.
- **Laptop B plays the SONACAM server** (Docker containers on Windows) and serves the web pages.
- A phone hotspot or Wi-Fi stands in for 4G. In the demo the meter listens continuously (10 s every 10 s) so changes show up quickly.

---

## 3. How it works

```
 IN THE BAR (the meter; Laptop A in the demo)  AT SONACAM (the server; Laptop B in the demo)     ON SCREEN
 ┌──────────────────────────────┐ 4G / WiFi ┌─────────────────────────────────────────┐   ┌──────────────────────┐
 │ microphone                   │  signed   │ 1. check the meter's signature          │   │ SONACAM dashboard    │
 │  → every 10 s: fingerprint   │ ────────► │ 2. match the fingerprint to a song      │──►│  live feed, map,     │
 │  → sign it (meter's own key) │  batches  │ 3. join matches into plays              │   │  songs, artists'     │
 │  → keep it until SONACAM     │           │ 4. write plays to the tamper-proof log  │   │  shares, flags       │
 │    confirms it was stored    │           │ 5. apply fair-play rules → shares       │   │ Artist page (phone)  │
 └──────────────────────────────┘           └─────────────────────────────────────────┘   └──────────────────────┘
```

- **No internet? No problem.** The meter keeps every batch until the server confirms it, then sends the backlog in order.
- **Songs are added** by artists or labels through the upload portal; the server fingerprints each song once.
- Detailed design: `docs/00_PROJECT_BRIEF.md`. Exact message formats: `docs/01_CONTRACT.md`.

---

## 4. Quick start (Windows)

**You need:** Windows 10/11, [Docker Desktop](https://www.docker.com/products/docker-desktop/) running, Python 3.11, Git.

### Start the server (Laptop B in the demo)
```powershell
git clone https://github.com/favour-tamfu/Fair_play.git
cd Fair_play
Copy-Item .env.example .env          # first time only; then set your own POSTGRES_PASSWORD (same value in DATABASE_URL) and ADMIN_TOKEN
docker compose up -d --build         # starts the database and the five server parts (first time: a few minutes)
docker compose ps                    # "api" and "db" should say (healthy)
```

### Load the songs and prepare the demo
```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e core -r server\requirements.txt
python -m server.tools.import_catalogue C:\path\to\Fair_Play_song_package   # the team's song package (not in git)
python -m server.tools.demo_seed     # checks and prepares the rest; every line should say OK
```
The song package is a folder with `catalogue.csv` and `audio/`. The server fingerprints the songs in about 2 minutes; `demo_seed` then builds the mock month on them.

### Open it
- Public landing page: **http://localhost:8000**
- SONACAM dashboard (unlisted address): **http://localhost:8000/sonacam-x7k2q9.html** (add `?period=mock_month` for the mock month)
- SONACAM admin page (unlisted; asks for the admin password): http://localhost:8000/sonacam-x7k2q9-admin.html
- Artists (public search) and one artist: http://localhost:8000/artist.html, **http://localhost:8000/artist.html?name=Locko&period=mock_month**
- Server health: http://localhost:8000/health

The unlisted addresses hide the SONACAM pages from the public site; they do not protect them. Admin actions are protected by the admin password (`ADMIN_TOKEN`).

### Let a meter connect (Laptop A on the same Wi-Fi or hotspot)
Run once in an **administrator** PowerShell: `powershell -ExecutionPolicy Bypass -File .\scripts\firewall_b.ps1`
(opens port 8000 on private networks only). Laptop A then sends to `http://<Laptop B's IP>:8000`.

### Stop
`docker compose stop` (data is kept) · start again with `docker compose start`.

---

## 5. The SONACAM server

### What each part does
The server is six small programs (Docker containers) that share one database.

| Part | Its job, in plain words |
|---|---|
| `db` | The database (PostgreSQL): songs, fingerprints, plays, the log, results. |
| `api` | The front door: receives meter batches and song uploads, answers the web pages, streams the live feed. |
| `worker_fp` | Learns each uploaded song: makes its fingerprint and checks it is not a copy of a song already in the catalogue. |
| `worker_match` | Recognises songs: compares each 10-second fingerprint from a meter with the catalogue. |
| `worker_play` | Turns recognised moments into plays ("song X played at bar Y from 21:03 to 21:07") and writes them to the log. |
| `scheduler` | Housekeeping: re-checks the log every 2 s, publishes an hourly checkpoint, refreshes the results every 5 min, watches which meters are online. |

### Everyday commands
| I want to… | Command |
|---|---|
| check everything before a demo | `python -m server.tools.demo_seed` |
| wipe the live test plays (keep songs, meters, mock month) | `python -m server.tools.demo_seed --reset-live` |
| load a song package (CSV + audio folder) | `python -m server.tools.import_catalogue PATH\to\package` |
| remove songs from the catalogue (e.g. test uploads) | `python -m server.tools.retire_songs S-000001..S-000012` (`--dry-run` to preview) |
| rebuild the mock month on the catalogue | `python -m server.tools.catalogue_month` then `python -m server.tools.import_mock data\mock_month_catalogue` |
| show the tamper alarm | `python -m server.tools.tamper --latest` · undo: `python -m server.tools.tamper --restore` |
| prove restarts lose nothing | `python -m server.tools.chaos run` |
| run the server tests | `.\scripts\test_b.ps1` |
| see a part's log | `docker compose logs -f worker_match` |
| hide the dashboard pages, keep the API | set `SERVE_WEB=0` in `.env`, then `docker compose up -d api` |

Times shown to people are Cameroon time (UTC+1); stored data and the API use UTC.

### API at a glance
Full shapes and examples: `docs/01_CONTRACT.md` and `contract/schemas/`.

**For meters** (every message is signed by the meter's own key)
| Endpoint | What it does |
|---|---|
| `POST /v1/batches` · `/v1/batches/bulk` | send fingerprint batches (one, or up to 50 when catching up) |
| `POST /v1/heartbeat` | "I'm alive", queue size; the answer carries the server's clock |
| `POST /v1/calibration` | known songs played near the meter → the meter's real catch rate |
| `POST /v1/meters/register` | register a meter's public key |

**For the pages**
| Endpoint | What it gives |
|---|---|
| `GET /api/v1/overview` | headline numbers (meters online, plays, songs, log status) |
| `GET /api/v1/artist-shares` | what each artist earned: their share of all counted plays |
| `GET /api/v1/shares` · `/api/v1/plays` · `/api/v1/flags` | per-song shares, recent plays, items flagged for review |
| `GET /api/v1/venues` · `/api/v1/artists/{name}` | bars and meters on the map · one artist's page |
| `GET /api/v1/compare-flat` | flat split vs Fair Play on the mock month (against what really played) |
| `GET /api/v1/ledger/status` · `/api/v1/ledger/anchors` | is the log intact? hourly checkpoints |
| `GET /api/v1/feed` | live feed (Server-Sent Events) |
| `POST/GET /api/v1/songs` | upload a song (with owners and consent) · list the catalogue |
| `GET /api/v1/export/usage_report.csv` | usage report: per song, plays and shares |
| `POST /api/v1/stats/run` · `POST /api/v1/demo/reset?confirm=yes` | recompute results now · wipe live test data |

Every list accepts `period=live|mock_month` and `mode=standardised|raw` (with or without the fair-play rules).

**Admin actions are protected.** Demo reset, recompute, approving a suspected duplicate, and adding a meter or changing its key need the header `X-Admin-Token` with the `ADMIN_TOKEN` from `.env`. Nobody else on the network can re-key a meter.

---

## 6. How the fair-play rules work

The goal: **a song counts for what people actually heard, and nobody can buy a bigger share by looping a song.**

### Step 1: count each play (rule version `sr-1.0`)
When the same song is repeated in the same bar, each repeat counts a little less:

| Play of the same song in a row | 1st | 2nd | 3rd | 4th | after that |
|---|---|---|---|---|---|
| Counts as | 1 | 1 | ½ | ¼ | 0, for a 2-hour cooldown |

The count starts again at 1 when the song comes back **after at least 30 minutes and 3 other songs**.
After the cooldown (2 hours and 3 other songs) the song counts normally again.

**Example (one bar, one night, from the project brief, test T-SR-1):** song A is played 7 times between 20:00 and 22:15, mixed with other songs → it counts as **3.75 plays**, not 7.

### Step 2: flag, don't punish
Some patterns are suspicious but can be innocent, so they are **shown to SONACAM for review** and never change the count by themselves:

| Flag | Meaning |
|---|---|
| loop | the same song back to back 4 or more times |
| low audience | played outside the bar's usual busy hours (e.g. 4 am to an empty room) |
| concentration | a song heard in very few bars with most plays in two of them |
| clock skew | a meter's clock is more than 5 s off |
| meter moved | a meter reports a different phone-network cell than where it was installed |
| duplicate suspected | an uploaded song looks like a copy of one already in the catalogue |

### Step 3: from plays to shares
- Each meter's plays are corrected for how many songs it misses (its **catch rate**, measured by calibration, 0.8 until then).
- A **song's share** = its counted plays ÷ all counted plays in the period.
- An **artist's share** = the sum of the shares of all their songs. This is what each artist truly earned. The dashboard can show the same results **Raw** (every play = 1) or **Standardised** (with the rules) side by side.

In this prototype each artist is registered as the 100 % owner of their songs, and no money is calculated: the result stops at each artist's share.

---

## 7. Trust: the tamper-proof play log

- Every play is chained to the one before it with a cryptographic hash (like numbered, sealed pages in a notebook). Changing any recorded play breaks the chain from that point.
- The server re-checks the whole chain continuously. **Measured: an edited play shows as "log broken" on the dashboard in about 1 second**, and results are withheld until the log is restored.
- Every hour a checkpoint of the log (a Merkle root: one short code that summarises all plays of that hour) is written to an append-only anchors file. In a real deployment it would go somewhere SONACAM does not control (for example a public blockchain), so even SONACAM could not quietly rewrite the past.
- A demo reset does not erase history silently: it starts a new "epoch" and writes the reset itself into the anchors file.

---

## 8. Measured during the hackathon

| What | Result |
|---|---|
| Restart test: every server part restarted while a meter was sending | 36 of 36 batches stored exactly once, 3 of 3 plays correct, log intact |
| Live meter during that test and a 20-minute server outage | 2,501 batches in a row, none missing, none duplicated |
| Song recognition time per 10-second window (66 songs in the catalogue) | median 13 ms, 95 % under 49 ms |
| Recognition of the 183-song catalogue (3 clips per song, clean audio) | 549 of 549 correct |
| Tamper alarm (edit a play → dashboard shows "log broken") | 0.9 s (restore → "intact" in 1.1 s) |
| Mock month (30 days, 31 bars, 183 songs by 61 artists, 71,957 recorded plays): import + results | about 15 seconds |

All numbers were measured on the two hackathon laptops. Accuracy through a real microphone in a noisy room: see [Device](#9-device-the-meter-software) (measured by A).

---

## 9. Device (the meter software)
*(Section owned by A: running the meter software on Laptop A, microphone check, virtual meters, calibration tool, measured accuracy.)*

## 10. Web pages
*(Section owned by A: SONACAM dashboard, artist page, upload portal, admin page.)*

---

## 11. Limits (what this prototype does not do)

- **No meter box yet.** During the hackathon, laptops stand in for the meter and for SONACAM's server (see [The real product](#2-the-real-product)); a phone hotspot or Wi-Fi stands in for 4G.
- **The mock month is simulated.** Bars, plays and listening patterns are generated (seeded, repeatable); only the songs are real. It exists to show what a month of data looks like and to compare the flat split with Fair Play against a known truth.
- **No money moves.** Results end at each artist's share; owners are set to the artist (100 %) as a placeholder until real splits are registered.
- **One credited artist per song.** Featured artists are not yet given their own share.
- **Recognition needs the song in the catalogue.** Music that was never uploaded is not counted and not recorded.
- **Catch rates are 0.8 until a meter is calibrated** on site with known songs.
- **Test keys only.** The meters' signing keys are prototype keys; a real deployment would provision them securely.

---

## 12. Declarations

All code in this repository was written during the hackathon (Mon 23 Nov – Wed 25 Nov 2026). **Built with Claude Code** (Anthropic), declared as an AI coding tool.

### Libraries and tools
| Library / tool | Version | Licence | Used for | Side |
|---|---|---|---|---|
| Python | 3.11 | PSF | everything | A, B |
| numpy | 2.1.3 | BSD-3-Clause | arrays, signal maths | A, B |
| scipy | 1.14.1 | BSD-3-Clause | spectrogram, filters, resampling | A, B |
| PyNaCl | 1.5.0 | Apache-2.0 | Ed25519 signatures (meter seals) | A, B |
| pydantic | 2.9.2 | MIT | checking message formats | A, B |
| httpx | 0.27.2 | BSD-3-Clause | sending batches, test client | A, B |
| FastAPI | 0.115.5 | MIT | server API | A, B |
| Uvicorn | 0.32.1 | BSD-3-Clause | web server | A, B |
| jsonschema | 4.23.0 | MIT | contract checks in tests | A, B |
| pytest | 8.3.3 | MIT | tests | A, B |
| psycopg | 3.2.3 | LGPL-3.0 | PostgreSQL driver | B |
| python-multipart | 0.0.17 | Apache-2.0 | song upload forms | B |
| pandas | 2.2.3 | BSD-3-Clause | results tables | B |
| sse-starlette | 2.1.3 | BSD-3-Clause | live feed | B |
| sounddevice | 0.5.1 | MIT | microphone capture | A |
| soundfile | 0.12.1 | BSD-3-Clause | reading WAV files | A |
| rich | 13.9.4 | MIT | meter status screen | A |
| tomli-w | 1.1.0 | MIT | meter config files | A |
| PostgreSQL | 16 (Docker image) | PostgreSQL Licence | database, fingerprint index, job queue | B |
| FFmpeg | Debian package in the server image | LGPL/GPL | decoding uploaded songs | B |
| Docker Desktop | — | Docker subscription terms | running the server | B |
| Leaflet | 1.9.4 (in `web/vendor/leaflet`, checked against the published integrity hashes) | BSD-2-Clause | street maps on the web pages | B |

### Data and assets
| What | Source |
|---|---|
| Song catalogue | 183 songs by 61 Cameroonian artists, compiled by the team for testing the prototype. Audio files are not in this repository. |
| Mock month | Generated by our code (`server/tools/catalogue_month.py`, seeded); bars, venue sizes and coordinates are illustrative. The repeated-song, promotion and empty-room scenarios use three fictional test tracks by "Fair Play test artist", so no real artist is shown gaming the system. |
| Album covers | Looked up through the public iTunes Search API (`tools/covers/`) and stored in `web/assets/covers/`. They belong to their artists and labels and are shown only next to those artists' own songs. |
| Photos | Pexels and Unsplash photos under their licences (credits in the landing page footer). |
| Map tiles | OpenStreetMap standard tiles, loaded from the internet when it is available (© OpenStreetMap contributors, ODbL; credited on each map). Without internet the pages show our drawn outline map. Add `?map=outline` to a page address to force it. |
| Fonts and icons | None bundled: the pages ask for SF Pro and fall back to the system font. |
| Test signals | Synthetic tones made by our code (`core/tests/data`). |
