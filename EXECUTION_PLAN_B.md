# EXECUTION PLAN — Agent B (Laptop B, SONACAM server, merge captain)

> Our working checklist, done step by step and together. Tick `[x]` only after the step's check has passed in this session.
> Source of truth for *what* to build: `docs/PLAN_B_SONACAM_SERVER.md`, `docs/00`, `docs/01`, `docs/02`.
> This file tracks *where we are*. Update it after every step.
> Repo: https://github.com/favour-tamfu/Fair_play (product name: **Fair Play**, replacing "SoundProof").

Legend: `[ ]` todo · `[~]` in progress · `[x]` done · `[-]` cut / skipped (give a reason)

---

## Situation at plan time (Mon 23 Nov, 21:17)

| Item | Found | Action |
|---|---|---|
| GitHub repo `favour-tamfu/Fair_play` | exists, **empty**, **PUBLIC** | Plan says private. Decide (D1) |
| Collaborator | `xlr8-bl2` already added (presumably Person A) | Confirm |
| `gh` CLI | logged in as favour-tamfu, `repo` scope | ok |
| Git 2.53, Python 3.11.0 (`py -3.11`) | installed | ok |
| `core.autocrlf` | **not set** | set to `false` (step 0.2) |
| Docker 29.5.2 | installed, **daemon not running** | start Docker Desktop (step 0.3) |
| ffmpeg on host | **not installed** | optional on B (the container has its own). Install for local tools (step 0.4) |
| Schedule | Plan assumed build starts Mon 12:00. It is **21:17 Mon** and the repo is empty → **~9 h behind** if build started at 12:00 | Re-baseline (D3) |

## Open decisions (answer before step 1)

- **D1 Repo visibility:** keep PUBLIC (simpler for judges) or make it private until submission? Nothing secret gets committed either way (`.gitignore` covers keys, audio, `.env`, `data/`).
- **D2 Rename SoundProof → Fair Play: how deep?**
  - *Recommended:* full rename now, before any code exists (cost is near zero now and grows later): brand "Fair Play", Python package `fairplay_core` (was `soundproof_core`), pip name `fairplay-core`, docs and kit files updated by search-and-replace, logged as `D-002` in DECISIONS.md so Agent A sees it. The rules module stays `server/stats/fairplay.py` (it is about fair-play *weights*, so the name still fits).
  - Alternative: brand-only rename (README, UI, pitch) and keep `soundproof_core` in code.
- **D3 Timeline:** did the build start at 12:00 today, or are the official times different? We re-time the merge checkpoints (MC0…MC5) with Person A when we know.

---

**Answers (Mon 21:20):** D1 = keep **PUBLIC**. D2 = **full rename** (`fairplay_core`, logged as D-002). D3 = **we start now (Mon ~21:20)**. The kit's clock times are **a guide only**: we work through the phases in order, and each merge checkpoint happens when both sides are ready for it (agreed with Person A at the time).

## Phase 0 — Prep on Laptop B (no product code)
- [x] 0.1 Answer D1, D2, D3. Record the answers in this file.
- [x] 0.2 `git config --global core.autocrlf false`
- [x] 0.3 Start Docker Desktop → `docker run hello-world` works
- [-] 0.4 (optional, deferred: the container has its own ffmpeg) `winget install Gyan.FFmpeg` (needed only for host-side tools such as `make_batches_from_wav` with mp3)
- [ ] 0.5 `w32tm /resync` (admin PowerShell) or Settings → Time → Sync now
- [ ] 0.6 Windows Mobile Hotspot: turn on once and note B's IP (usually `192.168.137.1`)

## Phase 1 — B-T00 Bootstrap the repo  → *tell A "repo is up"*
- [x] 1.1 Choose the local repo folder (proposal: `C:\Users\favou\Desktop\Fair_Play\repo`, kit files stay beside it) and `git clone` the empty repo there
- [x] 1.2 Folder layout from `docs/02 §1` (`core/`, `server/`, `device/`, `web/`, `tools/mockgen/`, `contract/{schemas,fixtures/{batches,api,mock_month},meters}`, `scripts/`, `handoffs/{A,B}/`) with `.gitkeep` / `__init__.py`
- [x] 1.3 Copy `docs/*` and `repo-root/*` into the repo, plus this plan; apply the D2 rename
- [x] 1.4 `.gitignore` and `.gitattributes` (exact lists in PLAN_B B-T00 and 02 §2)
- [x] 1.5 `core/pyproject.toml` (pins numpy 2.1.3, scipy 1.14.1, pynacl 1.5.0, pydantic 2.9.2), `constants.py` **verbatim** from contract §2, `__init__.py` exporting `FP_VERSION`
- [x] 1.6 `contract/CHANGES.md` (`## c-1.0 …`), `README.md` skeleton (pitch, Quick start placeholder, Declarations table, "Built with Claude Code"), `requirements-dev.txt`
- [x] 1.7 `scripts/test_b.ps1`
- [x] 1.8 venv: `py -3.11 -m venv .venv` → `pip install -e core` → `import` check
- [x] 1.9 Commit `[B-T00] bootstrap`, push `main`, create and push `a/work` and `b/work`
- [x] 1.10 Handoff `handoffs/B/<date>_<time>_B-T00.md` + STATUS_B; tell Person A (send them the START_HERE "Person A" message)
- **Check:** `git ls-remote` shows `main`, `a/work`, `b/work`; A has cloned.

## Phase 2 — B-T01 Core: schema, signing, landmarks  → **MC0**
- [x] 2.1 `schema.py`: `Batch`, `Heartbeat`, `Calibration` (pydantic v2), `canonical_bytes()`
- [x] 2.2 `signing.py`: `generate_seed`, `public_key_b64`, `sign_dict`, `verify_dict`, `load_pub`, `load_seed` (+ `sign_batch` / `verify_batch` aliases that PLAN_A uses)
- [x] 2.3 `landmarks.py`: `make_hashes`, `MemoryIndex`, `match_window` → `MatchResult`
- [x] 2.4 Tests: `test_schema.py`, `test_signing.py`, `test_landmarks.py` (hand-made hashes; synthetic 3-song match with shift 100, 30% dropped, 20% extra; random query rejected)
- [x] 2.5 JSON Schemas (draft 2020-12), all 13 files from contract §9
- [x] 2.6 Test vectors `tv_keys.json`, `tv_batch_valid/badsig/badversion.json`
- [x] 2.7 `scripts/cp0_b.ps1`; handoff; push `b/work`
- [x] 2.8 **MC0 merge** (`b/work` then `a/work` → `main`), joint test (same SHA from `extract_peaks` on both laptops, cross-verify a signature), tag `cp-0`
- **Check:** `pytest core -q` green on both laptops.

## Phase 3 — Server foundation  → **MC1**
- [x] 3.1 **B-T02** Docker Compose (db, api, worker_fp, worker_match, worker_play, scheduler), Dockerfile, migrations `001_init.sql`, `/health`, `firewall_b.ps1`
  - Check: `docker compose up -d` healthy; `curl localhost:8000/health`; A's netcheck green
- [x] 3.2 **B-T03** Ingest API (`/v1/batches`, `/bulk`, `/heartbeat`, `/meters/register`), meter key loading, SSE bus over Postgres NOTIFY, API fixtures for A, `send_fixtures.py`
  - Check: test vectors give 200, 401, 422; duplicate and 409 cases; `curl -N /api/v1/feed` shows `batch` events
- [x] 3.3 **B-T04** Song upload + fingerprint worker + duplicate check + `DbIndex` + `reindex_all`
  - Check: 3 songs → ready; re-upload → duplicate_suspected
- [x] 3.4 **B-T05** Matcher worker + `make_batches_from_wav.py`
  - Check: ≥90% of windows accepted on clean audio
- [x] 3.5 **MC1 merge** + joint live test (speaker → accepted matches for ≥2 of 3 songs; 2-minute network cut → no seq gaps), tag `cp-1`

## Phase 4 — Plays, ledger, read API, rules  → **MC2**
- [x] 4.1 **B-T06** Play logger (event time, chorus-safe, late batches, restart-safe, unidentified music) + its 6 tests
- [x] 4.2 **B-T07** Ledger chain, Merkle root, FileAnchor, auditor, `tamper.py`
- [x] 4.3 **B-T08** Read API v1 + SSE feed + static `web/`, responses checked against schemas
- [x] 4.4 **B-T09** Fair-play weights `sr-1.0` + modifiers; T-SR-1/2/3 exact
- [x] 4.5 **B-T10** Estimation + bootstrap ranges + `run_stats` + shares API (<20 s per mode on the mock month)
- [x] 4.6 **B-T11** Mock month importer (read from `origin/a/work` with `git show`) + compare-flat + migration 002 (chain namespace)
- [x] 4.7 **B-T12** Payouts (largest remainder, total == pot) + WIPO CSV + frozen — as decided in D-015: artist cumulative shares, no money
- [ ] 4.8 **MC2 merge** + joint test, tag `cp-2`. Keep the stack stable for the industry clinic

## Phase 5 — Polish features  → **MC3 / MC4**
- [ ] 5.1 **B-T13** `mode` everywhere, flags complete, demo reset, tamper SSE within 2 s → **MC3**, tag `cp-3`
- [ ] 5.2 **B-T14** Calibration intake, catch rates, clock_skew and meter_moved flags
- [-] 5.3 **B-T15** Sepolia anchor (*stretch; first to cut*)
- [ ] 5.4 **B-T16** Chaos and restart test, matcher latency, `demo_seed.py`
- [ ] 5.5 **B-T17** README (server), Declarations → **MC4**, full demo ×2, tag `cp-4`

## Phase 6 — Wednesday
- [ ] 6.1 **B-T18** Fixes only, fresh-clone test on Laptop A, tag `v1.0` (MC5), submit by 10:00

---

## Never cut (02 §9)
Live match · play on map · raw vs standardised · tamper demo · payouts total = pot.
Cut order if late: Sepolia → admin page → calibration UI → artist page polish → number of virtual meters.

## Log (append one line per finished step)
| When | Step | Result / evidence |
|---|---|---|
| Mon 21:17 | Plan created | Kit read in full; environment checked (table above) |
| Mon 21:25 | 0.1–0.3 | Decisions recorded; autocrlf=false; `docker run hello-world` → "Hello from Docker!" |
| Mon 21:30 | 1.1 | Cloned into `Fair_Play\repo`; branch `main`, no commits, origin = favour-tamfu/Fair_play |
| Mon 21:35 | 1.2 | Skeleton created: 14 placeholder files (`.gitkeep`s; `__init__.py` in `core/fairplay_core/` and `server/`) |
| Mon 21:33 | 1.3 | docs + kit files copied; rename applied (SoundProof→Fair Play, soundproof_core→fairplay_core, compare-flat field → `misallocated_fairplay_fcfa`); D-002, D-003 in DECISIONS.md. This plan now lives only in the repo |
| Mon 21:34 | 1.4–1.7 | .gitignore, .gitattributes, core/pyproject.toml, constants.py (diff vs contract §2: identical), CHANGES.md, README skeleton + Declarations, requirements-dev.txt, scripts/test_b.ps1 |
| Mon 21:35 | 1.8 | venv (Python 3.11.0); `import fairplay_core` → fp-1.0, 311 frames/window; test_b.ps1 → "no B tests exist yet" |
| Mon 21:36 | 1.9–1.10 | Pushed main/a/work/b/work @ 6162b9a; handoff B-T00 + STATUS_B on b/work. **Phase 1 done** |
| Mon 21:50 | 2.1 | `schema.py` (Batch, Heartbeat, Calibration, canonical_bytes, time helpers) + test_schema.py → 37 passed |
| Mon 21:54 | 2.2 | `signing.py` (Ed25519 sign/verify, key files, RFC 8032 vector) + test_signing.py → core total 65 passed |
| Mon 22:02 | 2.3–2.4 | `landmarks.py` (vectorised make_hashes = loop reference, MemoryIndex, match_window, slice_peaks) + test_landmarks.py → core total 107 passed. Synthetic margin: noisy slice 50/50 accepted (score ≥352), random 0/200 (max 5); 5-min song hashed in 33 ms |
| Mon 22:15 | 2.5 | 16 JSON Schemas (13 from §9 + songs, song, artists) + test_contract_schemas.py; clarifications logged in contract/CHANGES.md → test_b.ps1: 142 passed |
| Mon 22:19 | 2.6–2.7 | Test vectors (M-90, deterministic) + check_batch + golden_sha + cp0_b.ps1 (GREEN, golden SHA waits for A); R-001 to A; handoff B-T01. test_b.ps1 → 147 passed. **B-T01 done; next = MC0 when A is ready** |
| Mon 22:47 | 3.1a–c (written) | requirements, Dockerfile, compose (6 services), .env (local), config, 001_init.sql, migrate, job board, /health, worker stubs, firewall script, DB tests. Not yet run: **Docker Desktop stopped ("unable to start")**; DB tests skip (2 passed, 6 skipped) |
| Mon 23:05 | MC0 check of A | a/work @ 4615239: only A-owned files; core 154 passed on A's branch; golden SHA a0544f53… MATCH on Laptop B; 20/20 A-built batches = identical signatures, schema+model valid; M-07.pub.json valid. Bug found → R-002 (silence → loudness −240 dB → 422). Log times corrected to real commit times (earlier rows were estimates) |
| Mon 23:15 | 2.8 MC0 | main = b/work + a/work (clean), cp0_b.ps1 GREEN on main (core 154 passed, golden MATCH), tag **cp-0** pushed; b/work = main. D-004 MC0, D-005 Claude Code declared in README only (no commit trailers). **Phase 2 done** |
| Mon 23:25 | MC0 real-key check | A's `batch_M07.json` (saved locally in gitignored data/cp0/): `check_batch` → signature verified with committed `M-07.pub.json`; peaks (194) and loudness (−9.0) identical to Laptop B's own extraction of tone_mix.wav. **All MC0 items verified** |
| Mon 23:55 | test with A (prep) | `server/tools/match_offline.py` (no Docker needed): user WAV (68.9 s) self-test 12/12; simulated meter (start 3.7 s, noise −6 dB) 6/6 matched, but scores 11–78 vs threshold 8 → thin margin off the frame grid. Waiting for A's mic batches |
| Tue 00:05 | song fingerprint check with A | `w1tde-ZgpvbxiTQAZjm-4A.wav`: file SHA 3fa304f4…, peaks SHA 2dd8c9d2… (472 peaks), hashes SHA b157cc49… (2198) — **identical on A and B** (user confirmed) |
| Tue 00:20 | 3.1 B-T02 | Image built; `docker compose up -d` → 6 services up, api+db healthy; /health ok db:true; 001_init applied once (19 tables); restart keeps data; B tests 153 passed (DB tests now run). Pending network leg: `firewall_b.ps1` (admin) + A netcheck on hotspot |
| Tue 00:45 | 3.2 B-T03 | Ingest API live (batches/bulk/heartbeat/register), meter keys loaded at start-up (M-07), live feed via NOTIFY→SSE; send_fixtures on the real stack: 200/401/422 as contract, feed shows batch+meter events, late flag by event time; 15 API fixtures + feed sample for A (schema-valid). test_b → 189 passed |
| Tue 01:00 | 3.3 B-T04 | Upload API + fingerprint worker + duplicate check + DbIndex live. User WAV + 2 synthetic songs ready in ≤1.1 s each; re-upload → duplicate_suspected (3/3 slices). test_b → 205 passed |
| Tue 01:35 | 3.4 B-T05 | Matcher worker live: user WAV at 3.7 s + 10 dB noise → 6/6 MATCH, offsets advance with the clock, 1–30 ms/window, SSE match events. make_batches_from_wav + cp1_b.ps1 (GREEN). test_b → 212 passed. **B side ready for MC1** |
| Tue 01:50 | MC1 merge + 2-song test | main = 96e1244 (b/work; a/work had no new commits). test.wav 37.6 MB → 400 too big; test.mp3 → ready 1.3 s. Meter sim from original WAVs: song 12/12, position 11/12 (chorus repeat 117.5→170.2 s, for B-T06). **cp-1 tag waits for joint test with A** |
| Tue 02:15 | MC1 merge (A) + A-mimic | main 5984759 (A: 13 commits, runner/TUI/R-002 fix). core 154, golden MATCH, B 212, A 52. Upload cap 50 MB = c-1.1 PROPOSED (R-003). Ms. Jackson S-000009 ready; All Falls Down = dup of S-000007 (correct). A's device code → B: 57/57 batches byte-identical to B, 57/57 right song, 50/57 exact position (misses = ±52.7 s repeats on off-grid windows) |
| Tue 02:35 | half-hop index (D-006) | Catalogue indexes grid phases 0 and +128 samples; re-indexed live. A-mimic re-run: exact position 50/57 → **57/57**, weakest score 18–20 → **249–335**. Worst case (¼–⅜ frame off + 10 dB noise): 60/60 song + position, min 65. test_b → 214 passed |
| Tue 02:55 | 4.1 B-T06 | Play logger live: brief §6 + D-007 (strays never split plays), recompute-and-reconcile per venue-night, chained at confirmation, extents for growth, corrections never edits. Live evening with network cut: 3 plays, 0 corrections, 9 late batches slotted in. test_b → 237 passed |
| Tue 03:20 | 4.2 B-T07 | Auditor + Merkle + FileAnchor + scheduler + tamper tool live. Hour 01:00 UTC anchored (11 plays). Tamper rehearsal ×3: RED ~1.0 s, GREEN ~1.0 s, right play named. test_b → 248 passed |
| Tue 03:45 | 4.3 B-T08 | Read API v1 live (overview, venues, plays, shares, flags, payouts, compare-flat, artists, artist) + static web at /. 11 live responses schema-valid; live venue has coords. test_b → 257 passed |
| Tue 04:10 | live feed check | /api/v1/feed captured live: batch, meter, match, play, ledger (tamper red → restore green) events all shown live (synth_1 on M-90) |
| Tue 04:30 | 4.4 B-T09 | sr-1.0 weights + loop/audience/concentration (D-008). T-SR-1/2/3 exact; = reference algorithm on 9,000 random plays. test_b → 276 passed |
| Tue 04:50 | D-009 (user decision) | audience factor + concentration check = review flags only, no weight change (switch MODIFIERS_ADJUST_WEIGHTS, tested both ways). test_b → 278 passed |
| Tue 05:00 | 4.5 B-T10 | estimation (L, catch rate, strata, bootstrap 200), run_stats raw+standardised, POST /api/v1/stats/run, scheduler every 5 min (D-010). Live: 12 plays → 9.0 counted, shares with ranges. 300k-play compute ≈ 2 s. test_b → 289 passed |
| Tue 05:15 | M-07 seq check (user) | M-07 batches 5–93 stored with no gaps/duplicates/late; 1–4 never reached the server (first contact 04:37:57 heartbeat, meter reports 0 queued) → asked A to check outbox |
| Tue 05:40 | D-011 (user decision) | meter in every bar (no scaling, no ranges), no opening hours, unidentified music not recorded (migration 005 drops table). R-006 to A. Live: 17 plays → 10.25 counted. test_b → 283 passed |
| Tue 06:50 | MC1 merge #2 + start | main 176122d = b/work + a/work a8c8c50 (mock month, dashboard, portal, artist). c-1.1 accepted. R-003..R-005 answered. test_b 283 passed; A suites 88/89 (1 needs A's secret seed). Kick-off handoff B-MC1-start |
| Tue 07:43 | MC1 joint test (06:32–06:42 UTC) | PASS: 3/3 songs live via A's mic (S-000007, S-000012, S-000009); Wi-Fi cut 2 min 37 s → 15 queued batches 717–731 delivered in order, M-07 seq 5–747 0 gaps 0 dups, 0 corrections, ledger intact. cp-1 tag after A confirms |
| Tue 07:50 | D-012 (user) | clocks correct (UTC vs Cameroon UTC+1); server logs now Cameroon time (TZ=Africa/Douala), flag texts local; R-007 asks A to convert times on the pages |
| Tue 09:50 | Song package → catalogue | package fixes (KRYS M merged, Locko row, counts, manifest); import_catalogue tool: FP-001…060 → S-000013…072 all ready; duplicate check now needs slices in line (3 false alarms fixed); 180/180 clips recognised; R-008 (show % not FCFA). test_b 284 passed |
| Tue 10:15 | B-T11 mock month + compare-flat | migration 006 (chain namespace, mock_meters, window_slots, mock_truth); import 91 139 plays in 11 s incl. stats; compare-flat flat 40.58 M vs Fair Play 3.93 M FCFA misallocated (pot 100 M, 94 artists); loop song S-M0150 101 plays at AKWA01 → 31.75 counted (cooldown flag); quiet hours flagged 25/25; promo not flagged (R-009). D-013. test_b 290 passed |
| Tue 10:30 | D-014 mock month on the real catalogue (user) | catalogue_month.py (seeded) on A's bars/meters + 60 catalogue songs; imported 65 635 plays; loop S-000068 66 plays → 28 counted, loop flag ×9; quiet hours 210 plays flagged; compare-flat 24 artists: flat 40.29 M vs Fair Play 2.91 M FCFA misallocated; promo still unflagged (decision open). R-010. test_b 292 passed |
| Tue 10:50 | B-T12 per D-015 (user) | artists earn the sum of their songs' shares: GET /api/v1/artist-shares (24 artists, sum 1.0; Locko 17.47 %, 7 songs), artist page `share`, usage report CSV (WIPO Connect prototype, shares only), frozen on broken ledger; artist_owners tool (60 songs, artist 100 %); no money; c-1.3 PROPOSED, R-011. test_b 297 passed |
| Tue 11:20 | merge a/work + web for D-015 (user) | merged a1d00d4 (A's R-007..009 → R-012..014 answered; A's c-1.2 not adopted; B's → c-1.3); MC1 PASS both sides → cp-1; web edited with user approval: no FCFA, artist earnings panel, rules panels, Cameroon time (R-015) |
| Tue 11:35 | page fixes (user) | stale cached JS/CSS caused empty artist panel + visible 'withheld' banner → pages now served with Cache-Control no-cache; WIPO mention removed (page, CSV header, file name); artist earnings panel moved above the song detail |
