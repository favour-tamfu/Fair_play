# LIVE CONTEXT — Person A / Laptop A (read this first in any new session)
Last updated: 2026-11-25 01:05 (Cameroon time).

## 0. Latest events (newest first)
- 01:10 User said **"Not now"** to fixing the M-07 clock-drift bug (B's R-020). Leave it unfixed until asked; keep Laptop A awake during the demo.
  Local commits after the push (not on GitHub): aa8e632 and this update.
- 01:05 **a/work pushed to GitHub** (user's explicit OK for this push): origin/a/work = 5ed3504. Push URL switched back to
  `DISABLED-no-push-from-this-clone` afterwards; re-enable only on the user's say-so (`git config remote.origin.pushurl https://github.com/favour-tamfu/Fair_play.git`).
- **B's server answers again** (192.168.1.51:8000, checked 01:00). B's main is at dd42d2c: B loaded catalogue v3 (S-000073..S-000195, 549/549
  recognised), regenerated the mock month on 183 songs (D-021), added admin token + safe meter registration (D-020).
- Dry-run merge of a/work into origin/main: **only REQUESTS.md conflicts** (both sides appended). Request numbers collide:
  B's R-019 (catalogue 183, D-021) and R-020 (M-07 clock lag) vs A's R-019 (real names) and R-020 (meter exe). Renumber A's to R-021/R-022.
- **Bug reported by B (their R-020), not fixed yet:** M-07 window_start drifts hours behind real time after pauses/sleep
  (3 h 54 min). Cause: `device/agent/scheduler.py` windows = `t0 + samples/48000`, re-anchors only on a `None` gap. Fix: compare each
  block's wall time to `t0 + pos/CAPTURE_RATE`; if off by > ~1 s, re-anchor; add a test with a 60 s wall-clock jump. The packaged exe has
  the same bug (rebuild after the fix). Also keep Laptop A from sleeping during the demo.
- Next suggested steps: (1) fix the scheduler drift + test, (2) merge origin/main into a/work resolving REQUESTS.md (renumber), re-run
  tests, (3) test the pages live against B, (4) rebuild exe + bundle. This file is overwritten after every message so a new account/session
knows exactly where we are. Older dated handoffs in this folder are history; this file is the current truth.

## 1. Who and where
- Hackathon: CIMFEST 2026 (Mon 23 Nov 12:00 → **Wed 25 Nov 12:00**). Project: **Fair Play** — audio meters in bars fingerprint the
  music, SONACAM (Cameroon music rights society) splits the beer/drinks copyright levy by counted plays instead of flat.
- User = **Person A**, Laptop A (Windows, PowerShell). Repo `C:\Users\DELL\Projects\CIMFEST_HACKATHON\Fair_play`, branch **a/work**.
- Person B runs the SONACAM server (FastAPI + Postgres in Docker) on Laptop B, `http://192.168.1.51:8000`.
  **Unreachable since 2026-11-24 12:40** → everything on A is tested in mock mode (`?mock=1`) only.
- Read CLAUDE.md, docs/01_CONTRACT.md, docs/02_WORKFLOW_HANDOFFS_MERGES.md for rules. Ownership: A owns `web/`, `device/`,
  `tools/`, `contract/fixtures/mock_month/`; B owns `server/`, `contract/fixtures/api/`, schemas, `.gitignore`.

## 2. Hard rules from the user (follow exactly)
- **Never push.** pushurl is disabled; "Leave it local". Hand over to B by git bundle / zip (see §6).
- **Commit messages: no Co-Authored-By, no mention of Claude/Claude Code anywhere in the project.** Format `[A-xxx] …`.
- Never commit audio, recordings, keys (`*.seed`, `device/secrets/`), `.env`, `data/`, `device/state/`.
- Only show numbers the code computed. No SONACAM branding on the public landing page.
- Ask before downloading files. Don't run broad `taskkill`. Use **Haiku** for subagents.
- Design: Apple style (apple.com / Apple Music page values), no scroll animations, no counting-up numbers, few colours.
- **Update this file after every message** (user's instruction, 2026-11-25).

## 3. Commits (all local on a/work; never pushed — run `git log --oneline -15` for the newest)
Latest first: (this context file's own commits) · b3a1edc live context + tools/covers · f3d1c0a packaged meter exe · 56d9e58 handoff · 32273e3 landing Apple restyle · 0a84281 real song names ·
8d5e000 covers · 2885974 dashboard Apple style · fc5081e music landing/covers · 7950a96 artist page · 6209ad8 portal …
Tests at f3d1c0a: `scripts\test_a.ps1` → **88 passed**; `pytest --noconftest server/tests/test_api_fixtures.py -q` → **19 passed**.

## 4. What exists (web/ is served by B at `/`)
| Page | File | State |
|---|---|---|
| Public landing | web/index.html, css/landing.css, css/mbp.css, js/landing.js | dark Apple-Music-style; sections: photo hero + CodePen MacBook (static dashboard screenshot `assets/img/shot-dashboard.webp`) → "Start with Fair Play" cards (#111 band, 345px cards, paddle arrows) → figures (stat callouts) → "Fairer by design" (7,7× flat-vs-Fair-Play + map) → music tiles (stepped frames of top song's cover with sway + pause; catalogue cover wall; live plays in Apple "Sing" layout; "Top this month" streak card with circle covers) → trust chain → how it works → FAQ |
| Artists (public data pool) | web/artist.html, js/artist.js, css/pages.css | finder + Apple-Music artist page; real covers |
| Artist portal (private) | web/portal.html, js/me.js, js/portal.js | prototype sign-in by name (no password, R-018); only place to declare a song |
| SONACAM dashboard (secret URL) | web/sonacam-x7k2q9.html, css/app.css + css/dash.css, js/app.js | sidebar layout, figure cards, dot-matrix "Plays by artist" chart, who earned what, map, feed, Songs, Trust; Apple colours (blue #0071e3) |
| Admin (secret URL) | web/sonacam-x7k2q9-admin.html, js/admin.js | unchanged this session |
| Covers | web/assets/covers/*.webp + index.json, js/covers.js | 170/183 songs (163 exact); matched only to own artist |
- `web/js/api.js`: `get(name, period, mode)`; mock reads `contract/fixtures/api/*`; supports overview, venues, shares, flags, ledger_status, payouts, artist_shares, compare_flat, feed, **plays, songs** (added).
- Preview: `.claude/launch.json` in the PARENT folder (`CIMFEST_HACKATHON`), server "web-mock" on port 8080 → `http://localhost:8080/web/index.html?mock=1`, dashboard `…/web/sonacam-x7k2q9.html?mock=1&period=mock_month`. (Port 8765 is used by device/tools/monitor.py.)

## 5. Data
- Song catalogue v3: **183 verified Cameroonian songs, 61 artists** — metadata in `tools/covers/catalogue_v3/` (catalogue.csv, not_included.csv, duplicates.csv) and `tools/mockgen/real_songs.csv`; audio only in `Downloads\Fair_Play_song_package_v3.zip` (613 MB). B holds only the 60 v1 songs (S-000013…S-000072).
- Open catalogue questions for the user: Tayc (3 songs, French-born of Cameroonian parents) and Ines D (1) — keep or not?; FP-003 vs FP-006 (Blanche Bailly) may be the same audio — someone should listen; 86 "unknown" songs not researched further; owners/consent/ISRC/MoMo missing for all songs.
- Test data: mock month (`tools/mockgen/generate.py --seed 42`) and API fixtures (`python -m server.tools.make_api_fixtures`) use **real titles/artists**; loop/promo scenarios use fictional "Loop/Promo test track" by "Fair Play test artist" (never shown on the landing). Bars still "Mock bar …". Composer/producer "not yet declared".
- Cover pipeline scripts (were in temp scratchpad, now in repo): `tools/covers/` — cover_lookup.py (iTunes Search, metadata), cover_download.py (alias-aware artist check, WebP 300px), cover_merge.py, cover_missing.py, make_handover.py; covers.json / covers_research.json results.

## 6. Packages for B (in `C:\Users\DELL\Downloads`)
- `Fair_Play_handover_for_B.zip` (723.9 MB): README_HANDOVER.md, code/Fair_Play_a-work.bundle (a/work @ f3d1c0a), songs/v3 zip, meter/FairPlayMeter_windows.zip, covers/FP-xxx.webp + covers.csv, docs/.
- Note: the bundle inside the handover zip is at f3d1c0a; the standalone `Downloads\Fair_Play_a-work.bundle` is newer (rebuilt after each commit). Give B the standalone bundle too.
- `Fair_Play_a-work.bundle` (code only). B: `git fetch <bundle> a/work:refs/remotes/laptopA/a-work` then `git merge laptopA/a-work`.
- `FairPlayMeter_windows.zip` (63.9 MB): the listener as an exe (see §7).
- **If you commit again, rebuild the bundle and the handover zip** (`git bundle create …\Downloads\Fair_Play_a-work.bundle a/work`; `python -I tools\covers\make_handover.py <repo> <Downloads>`).

## 7. Packaged listener (device/packaging/)
- `FairPlayMeter.exe` = PyInstaller 6.11.1 build of `device/packaging/meter_app.py` (spec `FairPlayMeter.spec`, `build.ps1` → `dist\`, ignored).
- Commands: no args / `run` (listen to default mic; `--input file:<wav>`, `--mode field`), `setup` (makes the meter's own key in `device\secrets\`, prints public key to register on the admin page), `check` (lists mics, pings SONACAM `/api/v1/overview`).
- Tested from a clean folder against the fake SONACAM (`uvicorn device.tools.fake_sonacam:app --port 8777`, run inside the test folder so keys load from its `contract/meters`) → 1 window, signature verified, `acked: stored`. **Not tested with live mic against B.**

## 8. Requests to B (REQUESTS.md) — all unanswered
R-017 page addresses changed (`/` = landing, dashboard `/sonacam-x7k2q9.html`) · R-018 artist login for portal · R-019 real song names in mock month and B's fixtures (A edited B's `server/tools/make_api_fixtures.py` with the user's OK; B should re-import the mock month, maybe regenerate artist_shares.json) · R-020 packaged meter + `.gitignore` lines.

## 9. Open / next
- Hand the zip to B; when B is reachable: merge, re-import mock month, load v3 songs, register meter keys, test all pages live (SSE, tamper banner).
- User decisions pending: Tayc/Ines D, FP-003/006 listen check, the 13 songs without covers, rename "Mock bar" venues?
- Known gaps: headline font "SF Pro Plus Expanded" not installed (SF Pro Heavy used); frames tile is grey because Locko's top cover is B&W.

## 10. Last user requests (most recent last)
1. Rebuild dashboard like a reference image in "our colours", then Apple CSS → done.
2. Real songs instead of mock artists → done. Shorten landing → done. Apple accuracy for cards/figures/comparison/live tile, cooler gradient, circles → done.
3. Handoff + package everything for B (art included) → done. Package the listener → exe done.
4. Keep this live context file updated after every message (account switch coming) → done, and ongoing.
5. **"commit to b"** → pushed a/work to GitHub (5ed3504) after the user chose "Push to GitHub a/work".
