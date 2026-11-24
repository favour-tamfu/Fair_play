# Pending checks: A side and B side (keep this list up to date)

## 1. Sequence check on B (not done yet)
- Sequences to verify: 5 up to the last sequence A has sent (A's counter was 164+ at the third cut).
- Sequences 1 to 4 never went to B: they were local test runs against the fake SONACAM on port 8001.
- B runs these on Laptop B (credentials in B's .env):
  - received:  `SELECT seq, window_start FROM raw_batches WHERE meter_id='M-07' ORDER BY seq;`
  - matched:   `SELECT r.seq, r.window_start, m.accepted, m.song_id, s.title, m.confidence FROM raw_batches r LEFT JOIN match_events m ON m.raw_batch_id = r.id LEFT JOIN songs s ON s.song_id = m.song_id WHERE r.meter_id='M-07' ORDER BY r.seq;`
  - missing:   `SELECT s AS missing_seq FROM generate_series(5, <last seq>) s LEFT JOIN raw_batches r ON r.meter_id='M-07' AND r.seq = s WHERE r.seq IS NULL;` (should return 0 rows)
- Output still to be pasted back to A.
- **B result (2026-11-24 07:43, MC1):** M-07 seq 5–747: 0 missing, 0 duplicates; delayed batches arrived in order; ledger intact (handoffs/B/2026-11-24_0743_B-MC1.md, R-013 answer).
- **B result (2026-11-25 00:15, after the demo reset of 24 Nov 14:13):** M-07 seq 2997–5291 → 2 295 received, **0 missing**, all 2 295 matched (17 accepted, 2 confirmed plays: Caléçon and C'est Grave Ici, offsets in line with time = real plays, played quietly ~ −40 dB). Older rows were cleared by the reset (epoch 1).
- **NEW, needs A — window times fall behind the real time (R-020):** received_at − window_start grew from 17 min (13:14 UTC) to 34 min (15:00) to **3 h 54 min** (22:25 onwards), in steps, after pauses (no batches received 16:40–18:30 UTC, laptop likely asleep). The meter's queue is 0 and its heartbeat clock is right (skew −0.8 s), so these are not old windows being sent late: the windows are stamped wrong. Cause: `device/agent/scheduler.py` stamps window k as `t0 + samples_counted / 48000` and only re-anchors when the capture yields a gap (`None`); after sleep/hibernate the stream resumes without a gap, so every later window keeps the lost time.

## 2. MC1 recognition (done: met on 24 Nov, R-013; S-000007/S-000012/S-000009 retired since, D-020)
- Planned songs: `w1tde-ZgpvbxiTQAZjm-4A` (CC0), `Test Song 2` (S-000007), `team_test_03` (S-000012).
- Recognised so far: "Ms. Jackson (private test)" (S-000009), which is not a planned song.
- Need: at least 2 of the 3 planned songs accepted through the speaker and mic.

## 3. Network cuts on A (done, A side only)
- Cut 1: 12+ windows held, all sent after Wi-Fi came back.
- Cut 2: 12 windows held, 0 acked during the cut, all acked after.
- Cut 3: 12 windows held, 0 acked during the cut, first ack 11 s after Wi-Fi returned.

## 4. Open items
- Monitor: link each sequence to its match verdict (join on window_start). In progress.
- B's catalogue: the commercial recordings and test uploads S-000001…S-000012 were removed (D-020). Catalogue = 183 team songs (D-021).
- R-005 confirmed by B (24 Nov 06:50: sha256 match).
- Virtual meters (A-T07): next plan task after MC1.
