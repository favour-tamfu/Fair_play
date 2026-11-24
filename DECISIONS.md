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

## D-006 — 2026-11-24 02:35 — B — Catalogue indexes every song on two frame-grid phases (0 and half a hop)
- What: the fingerprint worker stores hashes of `extract_peaks(x8)` AND `extract_peaks(x8[128:])` (128 samples = half a hop) under the same song (`server/config.py FP_INDEX_SHIFTS = (0, 128)`). fp-1.0, the device and the contract are unchanged; the index is ~2× bigger.
- Why: a live meter window never starts on the catalogue's frame grid. Windows half a hop off scored 18–74 instead of 330–500 and, on repetitive songs, landed on another copy of a repeated section (±52.7 s in a looped track) — the play logger would have split one play into several.
- Measured on the live stack (A's own device code → B, 3 songs, 57 windows): exact position 50/57 → 57/57, weakest score 18–20 → 249–335. Worst case (window ¼ and ⅜ frame off + 10 dB noise, 60 windows, 2 songs): 60/60 right song and position, min score 65.
- Affects A: A-T16 evaluation harness should index songs with the same two shifts (or call `server.workers.fingerprint.song_hashes`) so measured accuracy reflects the server.

## D-007 — 2026-11-24 02:55 — B — Play logger: one off-track window never starts or splits a play
- Brief §6 starts a new play when the song offset jumps back > 20 s. On repetitive songs a single window can match another copy of a repeated section (seen live: ±52.7 s in a looped track), which would split one play into several and over-count the song.
- Rule implemented (server/plays/segment.py): an off-track window of the same song is held as "pending"; the NEXT accepted window decides — agrees with the open play → the pending window was a stray (ignored); agrees with the pending window → real: back > 20 s = restart (new play), otherwise a forward skip inside the same play. All other §6 rules unchanged.
- Effect: a genuine restart is confirmed one window (10 s) later; a stray never splits a play. Live proof: the pre-D-006 All Falls Down run with 7 stray windows → 1 play (15 windows), not several.
- Also: plays are hash-chained at confirmation (core fields fixed); what grows while the song keeps playing (end, windows, duration, loudness) is in `play_extents`, not in the chain. Affects A: GET /api/v1/plays duration_s will come from play_extents (B-T08).

## D-008 — 2026-11-24 04:30 — B — sr-1.0 modifiers: minimum-data guards and exact readings
- Streak/cooldown (§7.1) is implemented exactly as the reference algorithm; "3 other songs" = 3 plays of other songs in the venue (as the reference counts). Proven equal to a line-by-line transcription on 9,000 random plays (server/tests/test_fairplay.py), O(n) instead of O(plays × songs).
- Audience factor: the venue's 20th percentile is taken over its meters' **received windows** in the period (silence included), not over plays — otherwise 20 % of every venue's plays would always be halved. Guards: loudness test only with ≥ 60 windows (10 min of data) and a known play loudness; active-hours test only with ≥ 50 plays in the venue (with 11 plays every hour holds < 10 % and every play would be halved). Several conditions → still a single ×0.5.
- Concentration cap: median = median of weighted plays per (song, venue) pair over all songs in the period. Only applied when the period has ≥ 5 venues — with one live venue every song is "in < 5 venues" and would be capped/flagged.
- Loop flag = consecutive plays in the venue (no other song between), each start gap = song length ± 20 s (unknown length → 240 s). It adds the reason `loop`, no weight change.
- Reasons per play: `streak_1..4` | `cooldown`, then optional `loop`, `low_audience`, `concentration_cap`. Flags: one `cooldown` row per (venue, song) with zero-weight plays ("7 plays -> 3.75 counted, 2 in cooldown"), one `loop` row per run, one `low_audience` row per venue, one `concentration` row per song.
- Values are in server/config.py (STREAK_WEIGHTS … CONC_CAP_MIN, AUDIENCE_MIN_*).
