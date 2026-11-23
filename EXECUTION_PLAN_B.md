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
- [ ] 2.2 `signing.py`: `generate_seed`, `public_key_b64`, `sign_dict`, `verify_dict`, `load_pub`, `load_seed` (+ `sign_batch` / `verify_batch` aliases that PLAN_A uses)
- [ ] 2.3 `landmarks.py`: `make_hashes`, `MemoryIndex`, `match_window` → `MatchResult`
- [ ] 2.4 Tests: `test_schema.py`, `test_signing.py`, `test_landmarks.py` (hand-made hashes; synthetic 3-song match with shift 100, 30% dropped, 20% extra; random query rejected)
- [ ] 2.5 JSON Schemas (draft 2020-12), all 13 files from contract §9
- [ ] 2.6 Test vectors `tv_keys.json`, `tv_batch_valid/badsig/badversion.json`
- [ ] 2.7 `scripts/cp0_b.ps1`; handoff; push `b/work`
- [ ] 2.8 **MC0 merge** (`b/work` then `a/work` → `main`), joint test (same SHA from `extract_peaks` on both laptops, cross-verify a signature), tag `cp-0`
- **Check:** `pytest core -q` green on both laptops.

## Phase 3 — Server foundation  → **MC1**
- [ ] 3.1 **B-T02** Docker Compose (db, api, worker_fp, worker_match, worker_play, scheduler), Dockerfile, migrations `001_init.sql`, `/health`, `firewall_b.ps1`
  - Check: `docker compose up -d` healthy; `curl localhost:8000/health`; A's netcheck green
- [ ] 3.2 **B-T03** Ingest API (`/v1/batches`, `/bulk`, `/heartbeat`, `/meters/register`), meter key loading, SSE bus over Postgres NOTIFY, API fixtures for A, `send_fixtures.py`
  - Check: test vectors give 200, 401, 422; duplicate and 409 cases; `curl -N /api/v1/feed` shows `batch` events
- [ ] 3.3 **B-T04** Song upload + fingerprint worker + duplicate check + `DbIndex` + `reindex_all`
  - Check: 3 songs → ready; re-upload → duplicate_suspected
- [ ] 3.4 **B-T05** Matcher worker + `make_batches_from_wav.py`
  - Check: ≥90% of windows accepted on clean audio
- [ ] 3.5 **MC1 merge** + joint live test (speaker → accepted matches for ≥2 of 3 songs; 2-minute network cut → no seq gaps), tag `cp-1`

## Phase 4 — Plays, ledger, read API, rules  → **MC2**
- [ ] 4.1 **B-T06** Play logger (event time, chorus-safe, late batches, restart-safe, unidentified music) + its 6 tests
- [ ] 4.2 **B-T07** Ledger chain, Merkle root, FileAnchor, auditor, `tamper.py`
- [ ] 4.3 **B-T08** Read API v1 + SSE feed + static `web/`, responses checked against schemas
- [ ] 4.4 **B-T09** Fair-play weights `sr-1.0` + modifiers; T-SR-1/2/3 exact
- [ ] 4.5 **B-T10** Estimation + bootstrap ranges + `run_stats` + shares API (<20 s per mode on the mock month)
- [ ] 4.6 **B-T11** Mock month importer (read from `origin/a/work` with `git show`) + compare-flat + migration 002 (chain namespace)
- [ ] 4.7 **B-T12** Payouts (largest remainder, total == pot) + WIPO CSV + frozen
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
| Mon 21:45 | 1.3 | docs + kit files copied; rename applied (SoundProof→Fair Play, soundproof_core→fairplay_core, compare-flat field → `misallocated_fairplay_fcfa`); D-002, D-003 in DECISIONS.md. This plan now lives only in the repo |
| Mon 21:50 | 1.4–1.7 | .gitignore, .gitattributes, core/pyproject.toml, constants.py (diff vs contract §2: identical), CHANGES.md, README skeleton + Declarations, requirements-dev.txt, scripts/test_b.ps1 |
| Mon 21:55 | 1.8 | venv (Python 3.11.0); `import fairplay_core` → fp-1.0, 311 frames/window; test_b.ps1 → "no B tests exist yet" |
| Mon 22:00 | 1.9–1.10 | Pushed main/a/work/b/work @ 6162b9a; handoff B-T00 + STATUS_B on b/work. **Phase 1 done** |
| Mon 22:20 | 2.1 | `schema.py` (Batch, Heartbeat, Calibration, canonical_bytes, time helpers) + test_schema.py → 37 passed |
