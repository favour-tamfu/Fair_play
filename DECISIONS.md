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
- Reasons per play: `streak_1..4` | `cooldown`, then optional `loop`, `low_audience`, `concentration` (renamed by D-009). Flags: one `cooldown` row per (venue, song) with zero-weight plays ("7 plays -> 3.75 counted, 2 in cooldown"), one `loop` row per run, one `low_audience` row per venue, one `concentration` row per song.
- Values are in server/config.py (STREAK_WEIGHTS … CONC_CAP_MIN, AUDIENCE_MIN_*).

## D-009 — 2026-11-24 04:50 — B (Person B, human) — Audience factor and concentration check only flag, never cut the money
- What: brief §7.2 audience factor (×0.5) and concentration cap are still computed, but they only add a reason to the play and a row to the SONACAM review list (`flags`). They do **not** change `weight`. Streak/cooldown (§7.1, the rule agreed by the team) is the only automatic weight. Loop already worked this way.
- Why: applied automatically they penalise honest plays — a daytime or quiet bar has every play halved, and a regional artist (huge in one town's bars, rare elsewhere) looks exactly like "paid promotion" and loses money. "The machine flags, a human decides."
- Switch: `server/config.py MODIFIERS_ADJUST_WEIGHTS = False`; `True` restores the brief's original behaviour (tested both ways).
- Affects A: dashboard/rules text should describe audience and concentration as review flags ("flagged for SONACAM review"), not weight cuts; the mock-month "paid promotion spike" scenario still appears as a `concentration` flag. The headline demo ("15 plays → 3.75 counted · cooldown") is unchanged.

## D-010 — 2026-11-24 05:00 — B — Estimation details (brief §7.3) and stats runs
- **Partly superseded by D-011** (listening fraction, strata, bootstrap and escrow removed). The "Runs" bullet still holds.
- Listening fraction L = received windows × 10 s ÷ open seconds in the period. Open seconds = the venue's open hours (default 18:00–02:00 local) **plus every local hour-of-day in which the meter actually sent windows** (its "own activity profile", §7.3.1 — so the daytime CIMFEST table is not treated as closed). L is clipped to (0, 1]; a meter with no window data gets L = 1.
- Unknown stratum → the meter's venue is its own stratum; unknown `bars_in_stratum` → the meter represents 1 bar. Catch rate unknown → 0.8.
- Bootstrap: 200 resamples (seed 20261124) of meters within strata; 5th–95th percentile, widened if needed so the range always contains the point estimate. A stratum with one meter has no spread (range = point) — honest: one meter cannot tell us its own sampling error.
- Escrow share = unidentified music seconds ÷ (unidentified + identified play seconds), reported in `shares.escrow_share`; shares of identified songs still sum to 1 (escrow is not redistributed, §7.3.7). How the pot treats escrow is decided in B-T12.
- Runs: raw (every play 1, no rules, no flags) and standardised are separate runs; ids `R-yyyymmddHHMMSS` strictly increasing (never reused after pruning); last 3 runs kept per (period, mode). Each standardised run replaces the previous stats flags of its period. Scheduler: `live` every 5 min, only when plays changed; `mock_month`/`all` on import (B-T11) or `POST /api/v1/stats/run`.

## D-011 — 2026-11-24 05:40 — B (Person B, human) — A meter in every bar; no opening hours; unidentified music not recorded
- **Every bar has a meter** (full coverage, not a sample). National total of a song = the sum of its counted plays over all meters, corrected only for each meter's catch rate (`plays / c`). No strata scaling, no `bars_represented`, no bootstrap: `ci_low = ci_high = share` (there is no sampling error to show). `venues.stratum` / `bars_in_stratum` stay as descriptive fields only.
- **No opening hours.** There is no way to know when a bar is open; the meter transmits what it hears, and nothing heard = nothing counted. The listening fraction (brief §7.3.1) is removed; `venues.open_hour/close_hour` are unused. (The flag-only active-hours check of D-008/D-009 uses the hours of the bar's own plays, not opening times.)
- **Unidentified music is not recorded.** Not every sound is Cameroonian music, and a song that was not uploaded earns no back payment. The `unidentified` table is dropped (migration 005); `overview.unidentified_music_min` and `shares.escrow_share` are always 0 (fields kept so the contract shapes do not change). An unmatched window is simply not a play.
- Affects A: mock month — every venue is metered (plays_observed differs from plays_true only by catch rate / matching misses; no sampling of bars); dashboard — no range bars (or show them collapsed), no escrow / unidentified KPI. See REQUESTS R-006.

## D-012 — 2026-11-24 07:50 — B (Person B, human) — People see Cameroon time; data stays UTC
- Stored data, the API and IDs (`R-yyyymmddHHMMSS`) stay UTC (contract §1). Everything a person reads is shown in Cameroon time (Africa/Douala, UTC+1, no DST): server logs (compose `TZ=Africa/Douala` for the Python services; Postgres stays UTC), flag texts ("… (Cameroon time)"), B's handoffs/log rows. The web pages convert on display (REQUESTS R-007 to A).

## D-013 — 2026-11-24 10:15 — B — Mock month import: chain namespace, mock meters, window slots, compare-flat basis
- **Two ledger chains** (`plays.chain`, migration 006; the plan's "002_chain_namespace" became 006 because 002 was taken): `live` (meters, never wiped) and `mock` (mock month, rebuilt on every re-import, hash-chained in event-time order from its own genesis). The auditor walks each chain from its own genesis; anchors, the playlogger rebuild and the tamper tool use the live chain only.
- **Mock meters in `mock_meters`** (all 30, `catch_rate = catch_rate_true`, i.e. calibrated meters). `meters` gets source-mock rows only for IDs not already used: A's mock IDs M-11/M-12/M-13 are also A's real virtual meters (M-12/M-13 at other venues), whose rows (keys, last_seq) are kept. Stats for `mock_month` read catch rates from `mock_meters`.
- **windows_observed.csv stored as 10-minute slots** (`window_slots`), not expanded. Not used for the audience flag: A's slot loudness (≈ −22 dB at every hour) is on another scale than the plays (≈ −28 dB at V-YDE-BASTO1), so a slot percentile marked 38 % of plays "quiet". Mock month audience flag = active-hours test only (it catches the 04:00 quiet-hours scenario: 25/25 plays).
- **compare-flat** (brief §7.4) per artist of the mock catalogue: truth = share of `plays_true` (each 1); flat = 1/n_artists; Fair Play = latest standardised mock_month run; misallocated = 0.5 × pot × Σ|S − S_true|.
- Mock songs: source mock, status ready, no hashes (never matched live). Mock venues that already exist (live venue, A's virtual-meter venues) keep their source and get the descriptive fields.

## D-014 — 2026-11-24 10:30 — B (Person B, human) — The mock month uses the real song catalogue
- The demo mock month plays only the 60 uploaded catalogue songs (S-000013…S-000072, 24 artists), all of them; A's 200 "Mock Song" titles are no longer loaded. Generated by `server/tools/catalogue_month.py` (seeded; default seed 20261124) into `data/mock_month_catalogue/` (not in git: regenerate with the command), same CSV format as contract §7, loaded with `import_mock`.
- Reused from A as they are: venues.csv, meters.csv (bars, hours, sizes, catch rates). Random: popularity (Zipf-like × noise, local favourites per bar), open nights, gaps, catch misses, loudness, slots. Scenarios redrawn on the real songs: loop (back to back), promo (5 bars, last 7 days), quiet hours (04:00–05:00 local), power cut (one meter, 2 days). `scenarios.md` names the songs drawn.
- Catalogue songs keep their own rows (hashes, status) and are never wiped by a re-import; no owners are invented (none known). Pages show shares as percentages next to these real names (R-008); money examples in the pitch use fake names.
- A's original files in `contract/fixtures/mock_month/` still import (`python -m server.tools.import_mock`) for tests.

## D-015 — 2026-11-24 10:50 — B (Person B, human) — B-T12: artists earn a cumulative share; no money; mock ownership
- Earnings are **per artist**: an artist's share = the sum of the shares of all their songs (credited lead artist, `songs.artist_name`). `GET /api/v1/artist-shares` ranks the artists; the artist page gets `share`.
- **No money is computed in this version.** The system ends at what each artist truly earned (their cumulative percentage). The planned pot × share, owner splits, rounding, mock Mobile Money statements and `sent_mock` status are dropped; `amount_fcfa` fields stay in the shapes only so no page breaks (deprecated in c-1.3). Money examples belong to the pitch, with fake names, computed by the code if shown.
- **Mock ownership:** each catalogue song's artist is registered as its 100 % owner (`server/tools/artist_owners.py`, only where a song has no owners; no MoMo invented). The page shows the sharing rules (API `rules` text; SONACAM's own rules text to be supplied by Person B).
- **Frozen** stays: if the ledger is not intact, artist shares and the usage report are withheld (rows empty / "FROZEN").
- The usage report (prototype CSV) lists shares, not amounts. Not presented as any external format for now (Person B, 11:35).

## D-016 — 2026-11-24 11:55 — B (Person B, human) — No promotion flag; no rules panels on the page
- No new "sudden spike" / paid-promotion rule: sr-1.0 stays as it is (streak/cooldown weights; loop, low_audience, concentration review flags).
- The dashboard does not show the "How the share is computed" and "SONACAM sharing rules" panels. The API keeps `artist-shares.rules` (unused by the page).

## D-017 — 2026-11-24 12:20 — B — Demo reset = new live-chain epoch; per-chain ledger audit
- `POST /api/v1/demo/reset?confirm=yes[&reason=]` (server/demo.py) wipes the LIVE test data: live/virtual batches, match events, windows, chain-'live' plays (+ extents, corrections, weights), period-'live' stats, match/play jobs, playlogger state; meters' `queued` → 0. Kept: songs + hashes, owners, venues, meters (keys, last_seq), the mock month, catalogue flags.
- The live chain restarts from genesis in a new epoch (`ledger_epochs`, migration 007). Anchors of the previous epoch move to `anchors_archive` (their plays are gone, so they can no longer be re-checked) and an `{"event":"epoch",…}` line is appended to the public anchors file, so a reset is always on record, never silent.
- Auditor caches per chain: a chain is re-walked only when its SQL fingerprint changes. Measured on the demo DB (65 659 plays): tamper → SSE `ledger` broken in 0.88 s, restore → intact in 1.08 s; API status correct within 0.5 s.
- Fix: `anchor_closed_hours` counted plays of all chains per hour while anchors cover the live chain only (re-anchored the same hour every minute after the mock import, no new line published); now live only.

## D-018 — 2026-11-24 12:35 — B — Meter health: calibration catch rate, clock_skew and meter_moved flags (B-T14)
- Calibration (`POST /v1/calibration`, contract §4): an expected play is caught if the meter has an accepted match of that song whose back-computed song start (window_start − offset_s), or a live play whose started_at, is within **±60 s** (contract; the plan's ±90 s is superseded) of `played_at`. catch_rate = caught / expected → `meters.catch_rate` (used by the share estimate) only if ≥ 1 play was caught; a run with 0 caught is stored but not applied. Matching lags, so runs received in the last 10 min are re-evaluated every 15 s by the scheduler; re-posting a run_id re-evaluates it.
- `clock_skew` flag: |server − meter clock| > 5 s, from heartbeats (sent_at) or a batch whose window ends > 5 s in the future; at most one per meter per hour.
- `meter_moved` flag: a batch reports a cell_id different from the meter's registered one (first seen); once per (meter, new cell). The registered cell is not changed.
- Both are review flags only (no weight change), stats_run_id NULL, SSE `flag`; removed by the demo reset.

## D-019 — 2026-11-24 12:55 — B — Robustness results; API-only switch (B-T16)
- `SERVE_WEB` (compose env, from `.env`; default 1): 0 = the api serves the API only, dashboard pages off. Person B set `SERVE_WEB=0` at 12:40 (dashboard off, meters keep reporting). Set 1 + `docker compose up -d api` to show the pages again.
- Restart test = `python -m server.tools.chaos run` (Python instead of the planned scripts/chaos_b.ps1: it needs signed batches and DB checks). Measured: baseline 30/30 batches, 3/3 plays; chaos (worker_match, api, worker_play, scheduler, db restarted during the send, 4 meter retries) 36/36 stored once, 3 plays in order, 0 job errors, ledger intact. Laptop A's live M-07 kept sending through all restarts: seq 5–2505, 0 missing, 0 duplicates.
- Matcher latency (66 indexed songs, 1 385 989 hashes): median 13 ms, p95 49 ms per window; first window after a matcher restart waits for the index load (≈ 6.6 s).
- `python -m server.tools.demo_seed [--reset-live] [--reimport]`: one-command readiness check before rehearsals (≈ 5 s).

## D-020 — 2026-11-24 14:20 — B (Person B approved fixes 1, 2, 3, 10) — Admin token, safe meter registration, test songs retired
- `ADMIN_TOKEN` (in `.env`, never in git; empty = open, for developer laptops and tests): header `X-Admin-Token` required for POST demo/reset, stats/run, ledger/anchor, songs/{id}/approve. demo_seed reports FAIL if it is not set.
- `POST /v1/meters/register` without the token only accepts a record that changes nothing that matters (same key as stored, or a new meter whose key equals contract/meters/<id>.pub.json); anything else → 403 `admin_token_required`. A meter can no longer be re-keyed by someone else on the network.
- Database unreachable/restarting → HTTP 503 `{"error":"db_unavailable"}` with `Retry-After: 2` (was a 500 traceback).
- Test and commercial uploads S-000001…S-000012 (11 songs) retired with `server/tools/retire_songs.py`: demo reset first (live epoch 1, 32 live test plays removed, 7 anchors archived, recorded in the anchors file), then songs, fingerprints, owners, flags, shares and audio files removed. Test meters M-90, M-97, M-98 removed from the demo database. Catalogue = the 60 package songs only.
- Bug found and fixed while doing it: the demo reset deleted raw_batches before match_events (foreign key) — it only worked on test data without links; the test now links them like real data.
- Container logs capped at 3 × 10 MB per service (disk).
- README: new section "2. The real product" (meter box, server, dashboard, artist page); laptops described as the hackathon stand-ins.

## D-021 — 2026-11-24 16:40 — B (Person B: "process them and add") — Song package v3: catalogue 183 songs
- The team's package v3 (`partner_package_v3`, FP-001…FP-183) imported: FP-001…FP-060 already in (unchanged), FP-061…FP-183 → **S-000073…S-000195** (song_map.csv in the package). Catalogue = **183 songs, 61 artists**, all `ready`, 3 740 365 hashes; no duplicate suspected, 0 job errors.
- Package fixed before import: "Krys M" (FP-057 featured; second artist row in the SQLite) merged into **KRYS M** (same person, as in v1); MANIFEST updated. Songs in not_included.csv (incl. Tayc ×3, Ines D ×1 marked "needs team decision") are NOT imported.
- Recognition check: 3 clips (25/50/75 %) of each of the 183 songs → **549/549 right song**; weakest best/2nd ratio 2.4.
- Mock month regenerated on all 183 songs (same seed 20261124; D-014): 90 063 true / **71 957 observed plays**, 61 artists, shares sum 1.0; flags cooldown 73, loop 51, low_audience 28. New scenario songs: loop S-000083 (Zambe, Cysoul) at V-DLA-AKWA01; quiet hours V-DLA-DLA02 / S-000052; power cut M-20 (19–21 Nov).
- Mock ownership (D-015): the 123 new songs registered with their artist as 100 % owner.
- The catalogue range lives in `config.CATALOGUE_RANGE` / `CATALOGUE_SIZE` (demo_seed, artist_owners, catalogue_month defaults).

## D-022 — 2026-11-25 02:00 — B (Person B: "fix the issues") — Meter window clock, lag flag, fictional scenario tracks
- Meter (A's file, Person B approved): `Scheduler.windows` re-anchors window times to the wall clock when the counted time and a block's wall time differ by more than 1 s (sleep, stalled stream). Before, M-07 ran 3 h 54 min behind after Laptop A slept (R-020).
- Server: on a heartbeat from a live meter with queue 0, if its newest window started more than 180 s ago → `clock_skew` flag ("window times behind the real time, or it stopped listening"), at most once per hour (`WINDOW_LAG_MAX_S`).
- Mock month: the loop, promo and quiet-hours scenarios use fictional tracks S-M0901/02/03 by "Fair Play test artist" (A's idea, R-023), so no real artist is shown gaming the system. 69 834 observed plays; loop flags only on the test tracks.
- A's merge (886c003): new landing page at `/`, dashboard and admin at unlisted addresses (R-021); README updated (pages, album covers via iTunes Search, Pexels/Unsplash photos).

## D-023 — 2026-11-25 03:30 — B (Person B) — Landing page speaks to SONACAM and shows live + monthly data
- The public landing page is SONACAM's pitch page: it explains what Fair Play gives SONACAM; artists are one card and a link, not the main audience. Artist-facing content stays on artist.html and portal.html.
- Numbers come from the API for both periods (switch), never typed in. c-1.4 (venues `source`, `plays` per period) added for the map.

## D-024 — 2026-11-25 05:45 — B (Person B: "admins do not have access to live organised logs") — Activity log for admins
- New table `activity_log` (migration 009): one readable line per thing the system did. Written automatically for every live-feed event (meter report, song heard, play logged, flag, play-log check, shares recomputed) plus meters going online/offline (scheduler), refused device requests (unknown meter, bad signature, sequence conflict, invalid), admin actions done / failed / refused for a wrong password (middleware), and songs becoming ready or failing to fingerprint. Kept 14 days (pruned hourly).
- `GET /api/v1/admin/activity` (filters kind, level, meter_id, venue_id, q, after_id for live polling, before_id for paging) and `/activity.csv`, both behind the admin password. Not on the public SSE feed (refused attempts and IPs are admin-only).
- Admin page: "Activity log" panel — type buttons, level and meter filters, search, Live/Pause (polls every 3 s), Load older, Export CSV. The old "Activity" panel is now "Your actions" (this tab only).

## D-025 — 2026-11-25 06:00 — B (Person B: "OSM, fallback offline") — Street maps with OpenStreetMap
- `web/js/osm.js`: Leaflet 1.9.4 (stored in `web/vendor/leaflet`, BSD-2, hashes match the official SRI) + OpenStreetMap standard tiles. Used by the landing map tile, the artist page map and the dashboard map: each bar as a dot sized by its plays, popup with bar, city and plays; the dashboard pulses a bar when a play is logged.
- No internet (tile test fails within 4 s) or `?map=outline` → the pages keep the drawn outline map (cameroon.js), so the demo works offline.

## D-026 — 2026-11-25 06:45 — Person B — Artist listening detail is SONACAM-only; the public sees the ranking
- Public `artist.html`: the ranking (top 4 + full list with shares) only; rows are not links. Reason (Person B): detailed listening data per artist (which bars played which songs, when) could be mined by competing artists and exposes what each bar plays.
- New SONACAM page `sonacam-x7k2q9-artist.html?name=` (noindex, linked from the dashboard's "Who earned what"): the full analytics (key figures, plays by day, map, top songs, bars, recent plays), asking for the admin password.
- `GET /api/v1/artists/{name}` needs the admin password (contract c-1.5). `/api/v1/artists` (names, songs) and `/api/v1/artist-shares` (the ranking) stay public. The public anchors only carry hashes, never plays.

## D-027 — 2026-11-25 07:00 — B (Person B: build the release now, including A's executable) — Fair Play v1.0 packaging
- One system, three parts: SONACAM server (`FairPlay_Server_<v>.zip`: code, pages, `scripts\install_server.ps1`), meter (`FairPlayMeter_windows_<v>.zip`: A's PyInstaller build, device\packaging), documents (`FairPlay_Docs_<v>.zip`); `START_HERE.md` (docs\RELEASE_START_HERE.md) and `SHA256SUMS.txt`. Built by `scripts\make_release.ps1` into release\ (not committed). Not included on purpose: song package (audio and rights), .env, keys, database.
- `install_server.ps1`: checks Docker, creates .env with random passwords (never printed), builds and starts every part, imports and fingerprints a song package (`wait_fingerprints`), runs demo_seed, prints the addresses (local + LAN, WSL address skipped). The catalogue works with any song ids (CATALOGUE_SIZE optional); API and DB ports configurable (API_PORT, DB_PORT).
- Fresh-clone test (separate stack on port 8100, removed afterwards): all demo_seed checks OK, 183/183 songs, the same mock month (69 834 plays). It found 3 installer bugs (ANSI parsing of BOM-less scripts, inline Python quoting, writing song_map into the package) and 1 server bug (a job abandoned by a worker restarted mid-job was never retried; workers now requeue abandoned jobs every minute) — all fixed.
- Packaged meter tested against the fresh server: setup (own key), registration refused without / accepted with the admin password, 60 s of a catalogue song → 6/6 windows recognised as the right song (scores 392–495), 1 play logged, activity log lines. File input of MP3 needs ffmpeg on the laptop (microphone use does not).

## D-028 — 2026-11-25 07:30 — Person B — Role-based access: SONACAM (one role) and artists
- Roles: `sonacam` (staff and admins fused: the SONACAM app and every SONACAM-only API) and `artist` (upload songs with metadata; see their own songs only: status, plays counted, share; never other artists or bars). Meters keep their own keys.
- Sign-in page `login.html`; sessions in an HttpOnly SameSite=Lax cookie (12 h; only the SHA-256 of the token is stored); passwords hashed with scrypt (migration 010: users, sessions). Account `sonacam` = ADMIN_TOKEN; artists (prototype rule, Person B): user name = their artist name, password `SONACAM` (ARTIST_DEFAULT_PASSWORD); an artist account is created on first sign-in if the name has songs in the catalogue (artists are verified on SONACAM's site). The X-Admin-Token header still works for scripts.
- SONACAM-only: /plays, /flags, /payouts, /export/usage_report.csv, /artists/{name}, /admin/*, all admin actions; the live feed gives everyone else plays as song, artist and city only (no bar, meter, reports, matches, flags). Public: overview, artist-shares (ranking), compare-flat, venues, ledger status/anchors, songs list, /public/recent-plays (song, artist, city).
- Artists: `portal.html` (own songs, totals per period, upload with owners and shares; MoMo optional; the artist name is forced to their own). SONACAM pages (dashboard, admin, artist analytics) redirect to sign-in. Public ranking page `artist.html` removed (D-026 superseded for the public part); the landing page stays as the product page.
- Routine 15-s share recomputes are no longer written to the activity log or the dashboard's live list (they flooded both).

## D-029 — 2026-11-25 08:45 — B (Person B: fix the issues) — Review flags, retire meters, clearer SONACAM pages
- Flags can be marked reviewed (who, when, note) and reopened; the operations page hides reviewed flags by default and reviews a whole group of repeats at once (migration 011, c-1.6).
- A meter can be retired (Retire, confirmed by a second click): its reports and heartbeats are refused (403 meter_retired, in the activity log); a re-registration with the admin password restores it. The meters list shows each key's fingerprint (SHA-256, 16 characters); mock-month bars only on request.
- Catalogue: uploads waiting for SONACAM first (waiting for review, could not be read, processing, just uploaded), newest first, in plain words.
- Dashboard: the fictional test artist is not counted as an artist and is labelled "fictional test"; simulated bars shown as "Bar <City> 01"; jargon replaced (counting rules, fingerprint of each hour, public anchors file; no run ids); the small bars in the key-figure cards (a repeat of the chart) removed.
- Meter 3D model: renders and assembly video on the landing page ("Meet the meter.") and in the README; the renders still carry the old working name on the labels.

## D-030 — 2026-11-25 10:15 — Person B — Artists see when their songs were played (never where)
- `GET /api/v1/me/plays?period=` (artist only): plays per Cameroon day and the latest plays (song, time, weight, counted less) — never the bar, city or meter. `/me/songs` totals add `all_counted` (all artists' counted plays in the period).
- Portal: "When your songs were played" (chart by day with a scale, latest plays) and "How your share is computed" (heard → counted → compared → share, with the artist's own numbers).
- Play extents are written only when they change: the scheduler no longer recomputes live shares every 15 s with nothing new.


## D-031 (B, 2026-11-25) Overview: live activity on top, ranked bars, activity kept across refresh
- Overview order: key figures → "Right now" row (Live activity + map) → Plays by artist → Who earned what.
- Plays by artist is a ranked horizontal bar list (top 12; light = heard, dark = counted; count and share at the end; hover for details; table view kept). The dot matrix was hard to read.
- Live activity loads its last 40 entries from the activity log on page load (plays, heard, meters, flags, log), so a refresh keeps it; then the live feed continues.
- A "Hearing now" card updates the instant a meter recognises a song (match event); a counted play also refreshes the figures at once instead of waiting for the next recompute.

## D-032 (B, 2026-11-25) SONACAM dashboard: flat cards, no pills, bars out of 100 %, full song list
- One white surface per card (no grey card around a white card); no pill-shaped buttons or labels (8 px corners).
- Live activity: no coloured dots or row lines (alternate row tint instead); "Last heard / Hearing now" is a plain block with a left accent; top row cards share one fixed height.
- Share bars in Who earned what and Songs are out of 100 % of counted plays, no longer relative to the leader.
- Songs lists the whole catalogue: played songs ranked first, then "Not played in this period" (0 plays).
