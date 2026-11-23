# Handoff A-T02 recorder fixes — 2026-11-24 00:55 — Person A / Laptop A
Task: recorder bug fixes (gap handling, device check, debug folder)   Status: DONE (tests run here)

## What was done (facts only)
- Gap handling: when the mic queue is full and a block is dropped, the mic now yields a gap marker (None). The scheduler restarts its windows at the next block, so later window times stay correct.
- Device check: the WASAPI default input is used only if it opens at 48 kHz (sd.check_input_settings). Otherwise the default device is used, with no failing first attempt.
- Debug folder: --save-debug-wav writes to <repo>/data/debug regardless of the working folder.

## Files changed
- device/agent/scheduler.py (gap marker handling)
- device/agent/capture.py (dropped counter, gap marker, device check, DEBUG_DIR)
- device/tests/test_capture_fixes.py (new, 5 tests)

## Tests
- `python -m pytest device core -q` -> 203 passed
- Real device pick now None (default device) on this laptop
- CLI on the CC0 song, 25 s demo: 2 windows, 66 peaks each (unchanged)

## Not verified
- The gap path with a real full queue (needs a stalled consumer); covered only by the scheduler test with a synthetic marker.
- scripts/mic_check.py still has its own WASAPI pick (not changed).

## Next action
- Mic check with music vs silence (A-T02), then wait for B's ingest API for cp1_a.ps1.
