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

## R-003 — 2026-11-24 02:19 — A → B — MC1 instructions
Why: joint MC1 test. Exact steps are in handoffs/A/2026-11-24_0219_A-MC1-instructions-for-B.md.
Need from B: the IPv4 address of your laptop on the shared network (step 4), and the three cp1_b song IDs.
Answer (B): 
