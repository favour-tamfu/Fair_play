# LIVE CONTEXT — Person A / Laptop A — read this first, then continue from §1
Last updated: 2026-11-25 ~02:45 (Laptop A clock, Cameroon time; B's notes run ~6 h ahead).
**Process rule (user): update this file BEFORE starting each task (what you are about to do) and AFTER it (what happened),
and commit it locally each time** (`[A-HO] Live context: …`). It is the single source of truth for a new account/session.

---
## 1. RIGHT NOW (resume here)
- **2026-11-25 (B's public address live; it is only in `Downloads\for_laptop_A\READ_ME_LAPTOP_A.txt` — never commit it):**
  merged origin/main (e6d4705) into a/work locally. User chose B's "Way 2" (packaged meter) over repointing M-07, so
  M-07.toml was left as it was (still LAN). New meter **M-21** @ V-BUEA-CIMFEST unzipped to `C:\FairPlayMeter` (outside the repo),
  `setup` done (key + `contract\meters\M-21.pub.json` there), `check` → answers (HTTP 200). Funnel was briefly slow (~23 s
  replies, check timeout 5 s), then ~3 s again.
  M-21 (old folder build) still needs its key registered by hand if it is used.
- **Join with approval (R-033, user's call: "single file + approve on dash, meters could be smuggled"):** one-file
  `dist\FairPlayMeter.exe` (`build.ps1 -Url <address>` bakes the address in under build\, not git). Double-click → meter id →
  it POSTs `/v1/meters/join` signed with its own key, prints the key fingerprint, waits (every 15 s) until SONACAM approves on
  Operations > "Waiting for approval" (new panel), then listens. A edited B's server files for it (joins.py, migration 012,
  ops/ingest endpoints, registry.key_fingerprint) — **server tests not run on A (no Docker/psycopg); B must run test_b,
  merge and restart the api** before it works on the public server (live server answers 405 now → meter starts anyway).
  Exe tested: setup in an empty folder, address baked in, check HTTP 200. test_a 95 passed. Copy for the user:
  `Downloads\FairPlayMeter_one_file\FairPlayMeter.exe`; for B: `Downloads\Fair_Play_R-033_for_B.bundle`.
  **Pushed a/work (037bcff) at the user's request** so B can pull: B runs `git pull origin a/work` (or merges it into main),
  `scripts\test_b.ps1`, then restarts the api. Waiting on B's answer in REQUESTS R-033.
  **B has deployed it**: the public server answers /v1/meters/join (checked 2026-11-25 ~10:10).
- **Zero-question meter (user):** double-click → sets itself up (random free id M-2000..9999, bar V-BUEA-CIMFEST, built-in
  address) → "Waiting for approval from SONACAM" → once approved, listens in a background thread with a menu (status,
  pause/resume, check connection, details, stop). Approval remembered in `device\state\<id>.approved`; taken id → new id by
  itself; older server → checks approval via signed heartbeat. Meter-only change (`meter_app.py`, `run_pipeline(on_ready=)`),
  B needs nothing. test_a **98 passed**. New exe copied to `Downloads\FairPlayMeter_one_file\`. A trial run left test meter
  **M-8862** (fp 84f9 2b00 1b6a d4ce, key deleted) in SONACAM's waiting list → user should Reject it.
- Previously: pushed a/work to GitHub (origin/a/work = **220b117**) at the user's request.
- **Waiting on B**: start the public tunnel (Tailscale Funnel) per `deploy/PLAN.md` / REQUESTS **R-032** and share the
  `https://….ts.net` address. B's `main` on GitHub has moved on since our merge (origin/main = **35e7929**) — fetch and look
  before the next web change (`git fetch origin; git log --oneline a/work..origin/main`).
- **A's next steps once the address exists** (deploy/PLAN.md step 2):
  1. Set `DEFAULT_SONACAM` in `device/packaging/meter_app.py` to the address; rebuild `.\device\packaging\build.ps1`
     (B suggested a retry loop around the zip step and a README line that `--input file:*.mp3` needs ffmpeg — R-029).
  2. Existing meter: edit `sonacam_url` in `device\config\M-07.toml`; `FairPlayMeter.exe check`; register keys on the operations page.
  3. Test over the internet from a phone on mobile data (deploy/PLAN.md step 3).
- **Pushing**: push URL is set to `DISABLED-no-push-from-this-clone`. Push only when the user says so, then:
  `git config remote.origin.pushurl https://github.com/favour-tamfu/Fair_play.git; git push origin a/work; git config remote.origin.pushurl DISABLED-no-push-from-this-clone`.
  Local commits after 220b117 (live-context updates) are not on GitHub yet.

## 2. Project, people, places
- CIMFEST Hackathon 2026, Mon 23 Nov 12:00 → **Wed 25 Nov 12:00** (demo). **Fair Play**: small meters in bars fingerprint the music;
  SONACAM (Cameroon's music rights society) shares the drinks/beer copyright levy by counted plays instead of a flat split.
- User = **Person A**, Laptop A (Windows 10, PowerShell, Python 3.11 venv `.venv`, Docker Desktop installed).
  Repo `C:\Users\DELL\Projects\CIMFEST_HACKATHON\Fair_play`, branch **a/work**; GitHub `favour-tamfu/Fair_play`.
- Person B = SONACAM server (FastAPI + Postgres + 4 workers in docker compose) on Laptop B (LAN `http://192.168.1.51:8000`, reachable again).
- Rules files: `CLAUDE.md`, `docs/01_CONTRACT.md`, `docs/02_WORKFLOW_HANDOFFS_MERGES.md`. Ownership: A = `web/`, `device/`, `tools/`,
  `contract/fixtures/mock_month/`; B = `server/`, `contract/fixtures/api/`, schemas, `.gitignore`, compose. In practice B also edits web/
  (logged in REQUESTS) and A edited B's fixture generator once with the user's OK (R-023/old R-019).

## 3. User's standing instructions (follow exactly)
- **No Co-Authored-By lines; never mention Claude / Claude Code anywhere** in commits or project files. Commit format `[A-xxx] …`.
- Push only on the user's explicit OK (see §1). Hand-overs can also go by bundle/zip in `C:\Users\DELL\Downloads`.
- Never commit audio, keys (`*.seed`, `device/secrets/`), `.env`, `data/`, `device/state/`, `dist/`, `build/`.
- Only show numbers the code computed; simulated ones labelled. No SONACAM branding on the public landing (B has since aimed the
  landing at SONACAM — accepted by the user implicitly; ask before reverting).
- Ask before downloading files. Never broad `taskkill`. Use **Haiku** for subagents. Design = Apple (apple.com / Apple Music values),
  SF Pro fonts, few colours, no scroll animations, no counting-up numbers.
- **Update this file before and after every task** (§0 rule above).

## 4. Current web (after merging B's work; B's latest main may differ — check §1)
| Address | File(s) | What |
|---|---|---|
| `/` landing | index.html, css/landing.css, css/mbp.css, js/landing.js | dark Apple-Music style; photo hero + CodePen MacBook (screenshot `assets/img/shot-dashboard.png`); starter cards (#111 band, paddle arrows); figures with **Live / Last 30 days** switch (B); comparison 7,7× + OpenStreetMap; catalogue tile; live plays in "Sing" layout (city only, public feed `/api/v1/public/recent-plays`); top-artists streak card; "Meet the meter" (B, `assets/meter/`); trust; how; FAQ |
| `/login.html` | login.html, js/login.js, js/session.js | sign-in (B, D-028): SONACAM user `sonacam` + ADMIN_TOKEN; artists = artist name + `SONACAM` |
| `/portal.html` | portal.html, js/portal.js | artist portal (B's new version) |
| `/sonacam-x7k2q9.html` | css/app.css + css/dash.css, js/app.js | SONACAM dashboard: sidebar, figure cards, dot-matrix "Plays by artist", who earned what, map (OSM), feed, Songs, Trust; Apple colours |
| `/sonacam-x7k2q9-artist.html` | js/artist.js | artist detail, SONACAM only (B, D-026) |
| `/sonacam-x7k2q9-admin.html` | js/admin.js | operations (B): meters + key fingerprint/retire, register meter, activity log, review flags, catalogue, actions. **A restyled it**: SF Pro on every element, Apple panels/buttons (`body.d2.admin` block at the end of css/dash.css) |
- `js/api.js` mock mode (`?mock=1`) reads `contract/fixtures/api/*`; supports plays + songs. `js/covers.js` real album covers
  (`assets/covers/`, 170/183 songs). Preview: `.claude/launch.json` in the PARENT folder, server "web-mock" port 8080 →
  `http://localhost:8080/web/index.html?mock=1`. Port 8765 = device/tools/monitor.py (leave it).

## 5. Data
- Catalogue v3: **183 verified Cameroonian songs, 61 artists**. Metadata in `tools/covers/catalogue_v3/` and `tools/mockgen/real_songs.csv`;
  audio only in `Downloads\Fair_Play_song_package_v3.zip`. B has loaded all 183 (S-000073..S-000195; 549/549 recognised).
- Test data uses real titles/artists; loop/promo scenarios use fictional "Loop/Promo test track" by "Fair Play test artist" (hidden on public pages).
- Open questions for the user: Tayc (3 songs) / Ines D (1) keep?; FP-003 vs FP-006 (Blanche Bailly) same audio?; 13 songs without covers.

## 6. Listener (meter)
- `device/agent` (Python) and the packaged **FairPlayMeter.exe** (`device/packaging/`: meter_app.py setup/check/run, spec, build.ps1, README).
  Each copy makes its own key on `setup`; register the public key on the operations page. B tested the exe against a real server
  (6/6 windows matched) and **fixed the clock-drift bug** (R-029/R-020).
- Packages in Downloads: `FairPlayMeter_windows.zip`, `Fair_Play_a-work.bundle`, `Fair_Play_handover_for_B.zip` (older; rebuild with
  `python -I tools\covers\make_handover.py <repo> <Downloads>` if needed).

## 7. Going online — `deploy/PLAN.md` (request R-032)
- Constraints: no bank cards; tunnelling accepted **for the demo only** (SONACAM would host the same compose stack on its own servers).
- **Main: Tailscale Funnel on Laptop B** (`tailscale funnel --bg 8000`, stable `https://<laptop>.<tailnet>.ts.net`).
  Backup 1: Cloudflare quick tunnel (`cloudflared tunnel --url http://localhost:8000`; no live feed, new address each start).
  Backup 2: ngrok free static domain. Rejected: Oracle/Google/AWS (card), Render/Koyeb/HF (512 MB/no workers/paid), Cloudflare
  Containers (paid). Laptop B must stay on, plugged in, awake, online. **Nothing published yet.**

## 8. Demo film — `pitch/DEMO_FILM_TREATMENT.md`
- Direction 2 (preferred): open on SONACAM's promise ("payments every three months"; "The best is yet to come" — **quote not verified**,
  needs the user's source before attributing), the flat 27,000 FCFA reality (Oct 2025 communiqué), then the Fair Play journey, end on
  **"Here it is."** Direction 1: follow one song. 2:00 max, motion graphics, licensed music, animatic first.

## 9. REQUESTS.md (numbering after B's merge)
A's: R-021 page addresses, R-022 artist login, R-023 real song names (A edited B's fixture generator), R-024 meter exe, **R-032 deploy plan**.
B's: R-019 catalogue 183, R-020 clock drift, R-025..R-031 (landing/data edits, portal, activity log, OSM, artist detail SONACAM-only,
exe tested, roles/sign-in, operations fixes). Most "Answer (A, time)" lines are still empty — answer them when asked.

## 10. Recent history (newest first)
- Pushed a/work 220b117. Plan: tunnelling for the demo (Funnel main, Cloudflare quick tunnel/ngrok backups).
- No-card hosting research; Oracle dropped (no cards); Cloudflare free can't run our Python server.
- Merged B's main (5fb5af7); restyled B's operations page in SF Pro + Apple style.
- Deploy plan v1 (Oracle) → v2 (no card) → v3 (tunnel decision).
- Demo film treatment (two directions). Packaged meter exe (tested vs fake server). Handover zip for B.
- Landing Apple restyles; real song names in test data; album covers (170/183); dashboard rebuilt (sidebar, dot-matrix).
- Tests last run: `scripts\test_a.ps1` → **90 passed** (after the merge).

## 11. How to resume in a new session
Say: *"Read `handoffs/A/LIVE_CONTEXT_A.md` and continue from §1. Update it before and after every task."*
Then: `git status`, `git log --oneline -5`, `git fetch origin` and compare with §1.
