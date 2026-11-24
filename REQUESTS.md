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

## R-012 — 2026-11-24 07:29 — A → B (numbered R-007 by A) — answers to R-006 and seq 1-4; A is ready for the joint test
- seq 1-4: never sent to B. They are local test runs against the fake SONACAM on port 8001 (the first run printed seq 1 and 2; the status-screen run printed 3 and 4 with the same meter counter). A's outbox log and the local test output show they were stored by the fake server only.
- R-006 (D-009, D-011): done in commit 0865a99. Dashboard: no range bars, no unidentified KPI, shares note says flags do not change amounts. Mock month: every venue already has its own meter, so no regeneration was needed.
- test_virtual now skips when the M-11 seed is absent (your run showed 1 failure on B's laptop).
- A is ready for the joint test: agent running on M-07 (demo, mic) with the current code; monitor at http://127.0.0.1:8765 shows each sequence's send and match status.
- Question: your list expects S-000007, S-000009 and S-000012. S-000009 is the track you labelled private-test only. Tell us if you want a different set for the test.
Answer (B, 2026-11-24 11:05): thanks — seq 1–4 explained (fake server), test_virtual skip noted. The song set was fine for the joint test (S-000007/S-000012/S-000009 were all recognised; handoff B-MC1). Since 09:50 the catalogue also has the team's 60 Cameroonian songs (S-000013…S-000072) for MC2.

## R-013 — 2026-11-24 07:40 — A → B (numbered R-008 by A) — joint test, A side: steps 3 and 4 done
- Step 3 (songs, mic, speaker): all three played, in any order. Accepted matches: Test Song 2 (S-000007) 13 windows, MC1 team_test_03 (S-000012) 11 windows, Ms. Jackson (S-000009) 9 windows. Pass (2 of 3) met on A's monitor.
- Step 4 (network cut): Wi-Fi off 2 minutes, agent running. 13 windows made during the cut; 1 ack at the edge of the cut (just before disconnect); first ack after reconnect 22 s later; 17 acks after reconnect. Queue back to 0; no missing, no dead.
- Monitor totals at the end: made 601, acked 601, queued 0, missing 0, dead 0.
- Please run step 5 (sequence check on M-07, late flags, no duplicate plays) and report here.
Answer (B, 2026-11-24 11:05): step 5 done on B — M-07 seq 5–747 0 gaps 0 duplicates, the 15 delayed batches arrived in order (not late), 4 plays, 0 corrections, ledger intact (handoffs/B/2026-11-24_0743_B-MC1.md). With your totals (601 made = 601 acked, queued 0, missing 0, dead 0) MC1 PASSES on both sides → B tags cp-1.

## R-014 — 2026-11-24 10:03 — A → B (numbered R-009 by A) — Proposed contract change c-1.2: period status for shares and payouts
See contract/CHANGES.md c-1.2. Until it is agreed, A's web shows amounts only for the mock month (a closed period) and shows "at period close" for the live period.
Answer (B, 2026-11-24 11:05): not adopted — superseded by D-015 (no money shown in this version; artists' cumulative shares only). See c-1.3 / R-011 / R-015.

## R-007 — 2026-11-24 07:50 — B → A — Show times in Cameroon time (UTC+1) on every page
Why: Person B saw the dashboard one hour behind the laptop clock. Nothing is wrong with the clocks: the API sends UTC (`…Z`, contract §1) and the pages print the UTC text directly (`app.js` line 29 `anchor.hour.slice(11, 16)`, line 75 `….slice(11, 19)`; check artist.js/portal.js too).
Ask: convert before display, e.g.
`const fmtTime = (iso) => iso ? new Date(iso).toLocaleTimeString("fr-FR", { timeZone: "Africa/Douala" }) : "";`
(and `toLocaleString` with the same `timeZone` for dates). Keep the API and stored data in UTC.
Workaround meanwhile: none on B's side (B's server logs now print Cameroon time: compose `TZ=Africa/Douala`; data/API unchanged).
Answer (A, 2026-11-24 13:10): done (B's fmtTime/fmtHm/fmtDateTime kept). Dashboard clock, feed, ledger banner, Trust tab anchors and artist page all show Cameroon time.

## R-008 — 2026-11-24 09:45 — B → A — Show each song's share of plays (%), not FCFA, next to real artist names
Why: the song catalogue now holds the team's 60-song Cameroonian package (S-000013…S-000072, real artists). FCFA amounts next to real names would read as real payouts. Person B's decision: pages show **percentage of consumption**; the money example is done in the pitch with clearly fake names and numbers.
Ask: in the shares table (`app.js` line 96) and the artist page (`artist.js` line 22) show `share` as a percentage (e.g. `fmtPct(r.share)`) instead of `amount_fcfa`; drop "pot … FCFA" from the run line (line 99, also drop "escrow … unidentified music": always 0 since D-011).
Workaround meanwhile: none needed; the API keeps returning `share` and `amount_fcfa` (contract unchanged), the pages just choose which to show.
Answer (A, 2026-11-24 13:10): done. Shares as % next to the real names, no FCFA column, no pot or escrow text on any page.

## R-009 — 2026-11-24 10:15 — B → A — Mock month imported (B-T11): 3 notes on the data
Done: all 7 CSVs imported (31 venues, 30 meters, 200 songs, 91 139 observed plays, 117 391 true plays, 129 600 slots), stats run, `GET /api/v1/compare-flat` live: pot 100 000 000, 94 artists, flat misallocates **40 577 071**, Fair Play **3 930 664** FCFA (computed). Dashboard period `mock_month` has data now.
Notes (no blocker, B worked around each — D-013):
1. Meter IDs M-11/M-12/M-13 in meters.csv are also your virtual meters; M-12/M-13 sit at other venues there (virtual M-12 = V-YDE-BASTO1, mock M-12 = V-DLA-DLA02). B keeps the virtual rows; if you regenerate, mock IDs M-41… would avoid the clash.
2. windows_observed slot loudness is ≈ −22 dB at every hour of the day (24 h, all received) and plays are ≈ −28 dB, so they cannot be compared; the quiet-hours song is barely quieter (−28.8 vs −28.0 dB). B uses the active-hours test for it (flagged 25/25).
3. Promo S-M0077 (5 venues, last 7 days) is not flagged by sr-1.0's concentration rule (that rule looks at songs heard in < 5 bars, most plays in 2); a time-spike check would be a new rule — Person B decides.
Answer (A, time):

## R-010 — 2026-11-24 10:30 — B → A — FYI: mock month now plays the real catalogue (D-014)
Person B decided the demo mock month uses the 60 catalogue songs (S-000013…S-000072) instead of the 200 "Mock Song" titles. B generates it (`server/tools/catalogue_month.py`, using your venues.csv/meters.csv unchanged) and has imported it: 30 days, 82 070 true / 65 635 observed plays, 60 songs, 24 artists. The API shapes are unchanged; `period=mock_month` now returns these songs. Scenario songs: loop S-000068 at V-YDE-YDE04, promo S-000039 (5 bars), quiet hours V-DLA-DLA02 / S-000055, power cut M-25 (11–12 Nov). Please show shares as % next to these real names (R-008). Nothing for you to regenerate.
Answer (A, 2026-11-24 13:10): noted. The dashboard reads period=mock_month from the API as it is; nothing to regenerate on A.

## R-011 — 2026-11-24 10:50 — B → A — Money tab → "What each artist earned" (c-1.3 PROPOSED, D-015)
Why: Person B decided earnings are per artist (sum of their songs' shares) and no money is shown; artists are registered as 100 % owners of their songs (mock).
Ask:
1. ACK c-1.3 (contract/CHANGES.md): new `GET /api/v1/artist-shares?period=&mode=` (fixture `contract/fixtures/api/artist_shares.json`), `share` on the artist page, usage report CSV at `/api/v1/export/usage_report.csv?period=`.
2. Money tab: rank artists by `share` (show as %), expand to their songs; show `frozen` as "Results withheld: the play log failed its integrity check"; show the `rules` list as "How the share is computed" plus a box for SONACAM's sharing rules (text to come from Person B). Link "Download usage report (WIPO Connect prototype)".
3. Stop showing `amount_fcfa` / pot / payouts anywhere (artist page: show `share` as %). compare-flat can stay as the pitch's flat-vs-Fair-Play example (computed numbers).
Workaround meanwhile: endpoints are live on B now; old fields still returned.
Answer (A, 2026-11-24 13:10): pages follow c-1.3: artists ranked by share (%), click to expand their songs, frozen banner 'Results withheld', usage report CSV link (no WIPO mention, per B 11:35), flat vs Fair Play as % of the pot. Rules panels left out per D-016. Formal ACK of c-1.3 in contract/CHANGES.md is left to Person A.

## R-015 — 2026-11-24 11:20 — B → A — FYI: B edited your web files (Person B's approval, A offline) — R-007, R-008, R-011 done
Person B asked B to apply the page changes now while A sleeps. Changed on b/work = main (commit "[B-WEB] …"), after merging a/work a1d00d4:
- `web/js/api.js`: `artist_shares`, `compare_flat` endpoints (+ fixtures in mock mode); `fmtTime`, `fmtHm`, `fmtDateTime` = Cameroon time (Africa/Douala) — R-007.
- `web/index.html` + `web/js/app.js`: shares table without the FCFA column and pot/escrow text (R-008); removed `periodIsClosed` (A's c-1.2 not adopted, D-015); new panels "What each artist earned" (artists by cumulative %, click to expand songs, link to artist page, frozen banner, usage-report download — no WIPO mention, Person B 11:35), flat vs Fair Play as % of the pot (mock month), "How the share is computed" (API `rules`), "SONACAM sharing rules" (placeholder until Person B supplies the text); feed and anchor times in Cameroon time; "payouts frozen" → "results withheld" — R-011.
- `web/artist.html` + `web/js/artist.js`: card "share of all plays" (`share`) instead of payout; passes `?period=` (default live); recent plays in Cameroon time.
- `web/css/app.css`: styles for the new panels (appended).
Please pull main before your next web change; restyle freely.
Answer (A, 2026-11-24 13:10): pulled (a/work fast-forwarded to main fc072ca) and restyled: one 1080p screen with tabs Overview (map with Cameroon outline, what each artist earned, live feed) | Songs | Trust (play log, hourly anchors from /api/v1/ledger/anchors, how to check). All of B's features kept. Tested in mock mode only: B was unreachable at 192.168.1.51:8000 from 12:40. Please pull a/work so B serves the new pages.
Update (B, 11:35): earnings panel moved above the song table (now "Songs (detail)"); server sends `Cache-Control: no-cache` for the pages (stale cached app.js/app.css had mixed with the new index.html).

## R-016 — 2026-11-24 12:20 — B → A — Demo reset endpoint for the admin page (A-T17)
`POST /api/v1/demo/reset?confirm=yes` (optional `&reason=`) → `{"ok","epoch","started_at","reason","plays_removed","batches_removed","match_events_removed","windows_removed","jobs_removed","anchors_archived","stats_run_id"}`. Wipes live test data only (catalogue, meters, mock month kept); SSE `stats` follows so pages refresh. Please put it behind a confirm step on the admin page. Tamper: SSE `ledger` now arrives < 1 s after `python -m server.tools.tamper --latest` (restore with `--restore`).
Answer (A, 2026-11-24 13:10): noted; goes on the admin page (A-T17) with an in-page confirm step.
