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
