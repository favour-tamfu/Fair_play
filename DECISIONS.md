# DECISIONS (append-only — never edit old entries)

## D-001 — 2026-11-23 12:00 — A+B — Baseline decisions from the plan
- Two laptops: A = device (+ web, mock month, demo), B = SONACAM server (merge captain).
- Fingerprint fp-1.0 (landmarks), schema v1, contract c-1.0, fair-play rules sr-1.0 (streak 1,1,0.5,0.25 → 2 h cooldown with ≥3 other songs; normal reset 3 other songs + 30 min; no nightly cap).
- Transport HTTP POST + outbox for the demo (MQTT in production). PostgreSQL is storage, fingerprint index and job queue.
- Ledger anchors: FileAnchor default, Sepolia testnet stretch, no token.
- Network: Windows Mobile Hotspot on Laptop B (fallback phone hotspot), port 8000 open on Private profile.

## D-002 — 2026-11-23 21:40 — B — Project renamed SoundProof → Fair Play
- Brand everywhere: **Fair Play**. Repo: https://github.com/favour-tamfu/Fair_play (public).
- Python package `fairplay_core` (pip `fairplay-core`), path `core/fairplay_core/` — replaces `soundproof_core` in every doc.
- Contract c-1.0 field `misallocated_soundproof_fcfa` → `misallocated_fairplay_fcfa` (GET /api/v1/compare-flat). Renamed before any code existed, so c-1.0 stays.
- Unchanged: the hardware dossier file name `SoundProof-meter-design.pdf`; the server module `server/stats/fairplay.py` (fair-play weights).
Affects A: import `fairplay_core` (e.g. `from fairplay_core.peaks import extract_peaks`); the web shows "Fair Play".

## D-003 — 2026-11-23 21:40 — B — Build started Mon ~21:20; the kit's clock times are a guide
- The work order (tasks, merge checkpoints MC0–MC5) stays as planned. The times in the plans are only a guide.
- Each MC happens when both sides are ready, agreed by the two humans at the time. Hard deadline unchanged: submit by Wed 10:00.

## D-004 — 2026-11-23 23:15 — B — MC0 passed; tag cp-0
- main = b/work + a/work @ 8bb1525, tag `cp-0`. On Laptop B: `pytest core` 154 passed; golden SHA `a0544f5308ec8b93615efbe73df2a90ed8aeb2a45a11bd64e027eda4e5695f13` MATCH; test vectors OK; 20/20 batches built by A's `build_batch` verify with `fairplay_core.signing` (identical signatures) and pass schema + model.
- Open from MC0: R-002 (silent window loudness −240 dB → must clamp to −100). A to pull main and run `scripts\cp0_a.ps1`.
- `core/` is now shared and frozen (docs/02 §5): changes only via contract protocol.
Affects A: `git fetch; git merge origin/main` into a/work.

## D-005 — 2026-11-23 23:15 — A+B (humans) — Declare Claude Code in README only
- Claude Code use is declared once, in README → Declarations (hackathon rule: AI tools must be declared). No "Co-Authored-By"/AI trailers in commit messages from now on. Earlier commits are not rewritten.
