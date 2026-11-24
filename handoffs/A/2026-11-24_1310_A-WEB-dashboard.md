# Handoff A — 2026-11-24 13:10 — A-WEB: SONACAM dashboard restyle (A-T11/A-T13)

## Done
- a/work fast-forwarded to main fc072ca (B's web edits R-015, D-014..D-017 included).
- Dashboard rebuilt as one 1080p screen with three tabs:
  - **Overview**: venue map with a Cameroon outline (`web/js/cameroon.js`, hand-traced, approximate), city labels that avoid each other and the dots, live venue on top, ring and caption on each SSE `play`; "What each artist earned" (c-1.3, click to expand songs, frozen banner, usage report CSV, flat vs Fair Play as % of the pot with bars for the mock month); live feed that lists plays, songs heard, flags, log status, meters going online/offline, stats runs (10-second batches and "no song" windows are not listed; delayed batches are).
  - **Songs**: every song's share with review flags.
  - **Trust**: play log status, plays checked, latest chain hash, hourly anchors (`/api/v1/ledger/anchors`; mock mode falls back to the last anchor), "How to check it yourself".
- Header: Live/Mock month, Standardised/Raw (applies to both tables), Cameroon clock, ledger button (opens Trust). Keys 1/2/3 switch tabs, L/M switch period.
- KPI "artists with plays" = rows of artist-shares with counted plays > 0 (computed, not typed).
- Names are HTML-escaped. REQUESTS.md answers for R-007, R-008, R-010, R-011, R-015, R-016.

## Tests
- `scripts\test_a.ps1` → 88 passed.
- Browser, mock mode (`python -m http.server 8080` at repo root, `web/index.html?mock=1`): 1920×1080 and 1280×720 fit without page scroll; tabs, period, mode, artist expand, compare card OK; frozen state simulated (red banner, earnings withheld, Trust red); no console errors. Artist page at 375 px still renders.
- **Not tested against B**: 192.168.1.51:8000 did not answer (ping fails) from 12:40.

## Next action
- When B is back: B pulls a/work; open `http://192.168.1.51:8000/` and check live data, SSE plays on the map, tamper → red within 1 s.
- A-T17 admin page (meters table, demo reset with in-page confirm, R-016).
- Formal ACK of c-1.3 left to Person A.
