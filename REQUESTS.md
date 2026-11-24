# REQUESTS (cross-side asks — append-only; answer by appending under the request)

Format:
## R-001 — 2026-11-23 16:20 — A → B — <what you need>
Why:
Workaround meanwhile:
Answer (B, time):

## R-001 — 2026-11-23 23:30 — B → A — MC0 golden SHA: commit `core/tests/data/tone_mix.wav` and use one WAV-loading recipe
Why: at MC0 both laptops must get the same SHA-256 of `pack_peaks(extract_peaks(tone_mix))`. Different WAV loaders (soundfile vs scipy, int16 scaling) would give different samples and a false mismatch.
Proposal: B's checker `python -m server.tools.golden_sha` loads with `scipy.io.wavfile.read` → int16/32768 (int32/2**31, uint8 (x-128)/128, float as is) → float32, stereo → mean; 8000 Hz used as is, 48000 Hz → `resample_to_8k`. Please load the same way in `test_peaks.py`, write `core/tests/golden/tone_mix.sha256` (hex on the first line), and commit the WAV (synthetic tones only).
Note: `.gitignore` now ignores only the top-level `/data/` and allows `core/tests/data/*.wav` (all other .wav/.mp3 still ignored).
Also available for A: `contract/fixtures/batches/tv_*.json` (test meter M-90, key in tv_keys.json — test only) and `python -m server.tools.check_batch <batch.json> <pub.json>` to check one of your signed batches exactly like the server will.
Workaround meanwhile: cp0_b.ps1 prints "SKIP golden SHA" until peaks.py and the WAV exist.

## R-002 — 2026-11-23 23:05 — B → A — Silent windows: clamp loudness_db to −100..0 before signing
Why: `rms_dbfs` of digital silence returns −240.0. Contract §3.1 (and batch.schema.json) allows −100..0, so the server answers 422 and the device moves the batch to `dead`. Silence is real (virtual-meter gaps between songs, muted mic). Found by B running A's `build_batch` on `np.zeros(80000)` (a/work @ 4615239).
Ask: in `device/agent/batcher.build_batch`, use `max(-100.0, min(0.0, round(loudness, 1)))` (or clamp inside `rms_dbfs`), and add a test for a silent window.
Also (suggestion, not blocking): `batcher.sign_fields/canonical_bytes` duplicate `fairplay_core.signing.sign_dict/canonical_bytes`. They are identical today (B checked: 20/20 A-built batches give the same signature as `sign_dict`, and validate against schema + model). Switching to the core functions avoids future drift.
Workaround meanwhile: none needed until A sends silence; B will not relax the contract range.
Answer (A, time):

## R-003 — 2026-11-24 02:00 — B → A — ACK contract change c-1.1: upload limit 50 MB (see contract/CHANGES.md)
Why: full-length WAV exports (~38 MB) were refused at 30 MB.
Ask: append `ACK c-1.1 — time — A` under the proposal in contract/CHANGES.md (or object), and use 50 MB in the portal check.
Workaround meanwhile: none needed; the server already accepts up to 50 MB.
Answer (A, time): ACK given in contract/CHANGES.md, 2026-11-24 05:18 (recorded by B at the MC1 merge; c-1.1 now in docs/01).

## R-006 — 2026-11-24 05:40 — B → A — Team decisions D-009 and D-011 change what the mock month and dashboard show
Why: Person B decided (DECISIONS D-009, D-011): every bar has a meter; no opening hours; unidentified music is not recorded; audience/concentration only flag for review.
Ask:
1. Mock month (A-T08): every venue is metered — no sampling of bars, no listening-fraction effects; `plays_observed` differs from `plays_true` only by catch rate / matching misses. `bars_in_stratum` is descriptive only. No unidentified-music figures needed.
2. Dashboard: no range bars (ci_low = ci_high = share), no escrow / "unidentified music" KPI (both always 0); describe loop/low_audience/concentration as "flagged for SONACAM review", not weight cuts.
Workaround meanwhile: the API already returns these values; fixtures in contract/fixtures/api were regenerated.
Answer (A, time):

## R-003 — 2026-11-24 02:19 — A → B — MC1 instructions
Why: joint MC1 test. Exact steps are in handoffs/A/2026-11-24_0219_A-MC1-instructions-for-B.md.
Need from B: the IPv4 address of your laptop on the shared network (step 4), and the three cp1_b song IDs.
Answer (B): see R-004 (same question).

## R-004 — 2026-11-24 05:18 — A → B — MC1 instructions (numbered R-003 by mistake; B's R-003 stands)
See handoffs/A/ for the MC1 instructions. Need from B: your IP on the shared network, and the three song IDs from cp1_b.
Answer (B, 2026-11-24 06:50): B is at **http://192.168.1.51:8000** (Wi-Fi; your M-07.toml already uses it; hotspot later = 192.168.137.1). Song IDs: team_test_01 → **S-000010**, team_test_02 → **S-000011**, team_test_03 → **S-000012**. ⚠ S-000010/S-000011 were flagged `duplicate_suspected` (copies of S-000007 All Falls Down / S-000009 Ms. Jackson already in the catalogue — commercial tracks, private test only, never in demo/video, brief §13), so they are not indexed under the new IDs; matches report S-000007/S-000009. Only S-000012 is new. Please bring 2 rights-cleared songs for the demo.

## R-005 — 2026-11-24 05:31 — A → B — MC1 songs for cp1_b (files are NOT in git; copy by USB into data\songs\)
Files (sha256 in contract/fixtures/audio/manifest.csv):
- team_test_01.wav (37.6 MB)
- team_test_02.mp3 (6.8 MB, converted from a 50 MB WAV for the 50 MB upload limit)
- team_test_03.mp3 (6.8 MB, converted from a 50 MB WAV)
Please check the sha256 of each copy, then run: .\scripts\cp1_b.ps1 -Songs data\songs\team_test_01.wav,data\songs\team_test_02.mp3,data\songs\team_test_03.mp3
Answer (B, 2026-11-24 06:50): uploaded 04:34 UTC. sha256 of the stored files = manifest exactly (8fd10da5…, 4a790fbc…, e68b860d…). IDs and duplicate note in R-004.

## R-007 — 2026-11-24 07:50 — B → A — Show times in Cameroon time (UTC+1) on every page
Why: Person B saw the dashboard one hour behind the laptop clock. Nothing is wrong with the clocks: the API sends UTC (`…Z`, contract §1) and the pages print the UTC text directly (`app.js` line 29 `anchor.hour.slice(11, 16)`, line 75 `….slice(11, 19)`; check artist.js/portal.js too).
Ask: convert before display, e.g.
`const fmtTime = (iso) => iso ? new Date(iso).toLocaleTimeString("fr-FR", { timeZone: "Africa/Douala" }) : "";`
(and `toLocaleString` with the same `timeZone` for dates). Keep the API and stored data in UTC.
Workaround meanwhile: none on B's side (B's server logs now print Cameroon time: compose `TZ=Africa/Douala`; data/API unchanged).
Answer (A, time):
