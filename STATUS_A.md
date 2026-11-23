# STATUS A — updated 2026-11-24 00:00
Current task: A-T02 Audio capture + scheduler (PARTIAL: file input verified, mic check pending)
Done: A-T00, A-T01 (fairplay_core.peaks; loudness clamped -100..0), MC0 script (cp0_a), CC0 test song manifest
Next up: A-T02 mic check with music playing, then A-T03 key provisioning and batch builder
Next merge checkpoint: MC1 (Mon 17:30 plan time) — not scheduled yet; needs B's ingest API
Blockers: none on A. MC0 not yet confirmed by B (B has to run cp0_b on its laptop)
Open requests to B: none
Health: device\tests\test_capture.py → 7 passed; file-input capture → 2 windows, 66 peaks each
Local-only: commits 93d28e9, ce21022, 8ac0ffe, not pushed
