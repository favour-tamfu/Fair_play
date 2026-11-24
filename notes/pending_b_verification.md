# Pending checks: A side and B side (keep this list up to date)

## 1. Sequence check on B (not done yet)
- Sequences to verify: 5 up to the last sequence A has sent (A's counter was 164+ at the third cut).
- Sequences 1 to 4 never went to B: they were local test runs against the fake SONACAM on port 8001.
- B runs these on Laptop B (credentials in B's .env):
  - received:  `SELECT seq, window_start FROM raw_batches WHERE meter_id='M-07' ORDER BY seq;`
  - matched:   `SELECT r.seq, r.window_start, m.accepted, m.song_id, s.title, m.confidence FROM raw_batches r LEFT JOIN match_events m ON m.raw_batch_id = r.id LEFT JOIN songs s ON s.song_id = m.song_id WHERE r.meter_id='M-07' ORDER BY r.seq;`
  - missing:   `SELECT s AS missing_seq FROM generate_series(5, <last seq>) s LEFT JOIN raw_batches r ON r.meter_id='M-07' AND r.seq = s WHERE r.seq IS NULL;` (should return 0 rows)
- Output still to be pasted back to A.

## 2. MC1 recognition (not met yet)
- Planned songs: `w1tde-ZgpvbxiTQAZjm-4A` (CC0), `Test Song 2` (S-000007), `team_test_03` (S-000012).
- Recognised so far: "Ms. Jackson (private test)" (S-000009), which is not a planned song.
- Need: at least 2 of the 3 planned songs accepted through the speaker and mic.

## 3. Network cuts on A (done, A side only)
- Cut 1: 12+ windows held, all sent after Wi-Fi came back.
- Cut 2: 12 windows held, 0 acked during the cut, all acked after.
- Cut 3: 12 windows held, 0 acked during the cut, first ack 11 s after Wi-Fi returned.

## 4. Open items
- Monitor: link each sequence to its match verdict (join on window_start). In progress.
- B's catalogue: "All Falls Down (private test)" and "Ms. Jackson (private test)" are commercial recordings. B's decision whether to remove them.
- B has not yet confirmed R-005 (MC1 songs as mp3 uploads).
- Virtual meters (A-T07): next plan task after MC1.
