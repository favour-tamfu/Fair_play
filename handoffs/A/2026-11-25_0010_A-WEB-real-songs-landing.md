# Handoff A-WEB — 2026-11-25 00:10 — Person A / Laptop A
Task: A-WEB site + A-T10 mock month with real song names   Status: PARTIAL (all pages built; not yet run against B)
Contract version in use: c-1.3   fp_version: fp-1.0   Branch: a/work   Last commit: see `git log -1` (this handoff commit)

## What was done (facts only), since handoff 2026-11-24_2346
- Real song names everywhere instead of "Mock Artist / Mock Song":
  - `tools/mockgen/real_songs.csv` (new): the 183 verified catalogue songs (id, title, artist, duration; no audio).
  - Mock month regenerated (`contract/fixtures/mock_month/`): 185 songs = 183 real + 2 fictional test tracks
    (S-M0077 "Promo test track", S-M0150 "Loop test track", artist "Fair Play test artist") so no real artist is shown cheating.
    Composer/producer owners are "not yet declared"; MoMo numbers stay synthetic. Bars are still "Mock bar …".
  - B's `server/tools/make_api_fixtures.py` edited by A with Person A's OK (R-019): 12 real artists and titles, loop song S-M0015
    is the test track, sample feed replays a real song. `contract/fixtures/api/*` regenerated (not artist_shares.json).
- Album covers: research pass added 19 songs; 170 of 183 have a cover (163 exact). KO-C accepted as Kocee (catalogue alias).
- Dashboard (`sonacam-x7k2q9.html`) restyled with the landing's Apple values (sidebar, #f5f5f7 cards, SF Pro figures, blue chart).
- Landing (`index.html`) shortened and reordered: hero + laptop (CodePen mockup, static dashboard screenshot), starter cards
  (Apple "get started" values, paddle arrows), figures, flat-vs-Fair-Play + map, music tiles (stepped frames, cover wall,
  live plays in the Sing layout, top artists), trust, how it works, questions.
- `web/js/api.js`: `get("plays")` and `get("songs")` added (mock and live: `/api/v1/plays?period=&limit=20`, `/api/v1/songs`).
- SONACAM research report committed: `reports/SONACAM royalties and Fair Play fit.md` + `research_notes/…`.

## Files created/changed
- tools/mockgen/real_songs.csv (new), tools/mockgen/generate.py, contract/fixtures/mock_month/*
- server/tools/make_api_fixtures.py (B-owned, R-019), contract/fixtures/api/* and README.md
- web/index.html, web/css/landing.css, web/css/mbp.css, web/css/dash.css, web/js/landing.js, web/js/api.js, web/assets/covers/*
- REQUESTS.md (R-019), reports/, research_notes/

## How to run it (exact commands, PowerShell, from repo root)
```
python -m http.server 8080
# http://localhost:8080/web/index.html?mock=1
# http://localhost:8080/web/sonacam-x7k2q9.html?mock=1&period=mock_month
python -m tools.mockgen.generate --seed 42 --out contract/fixtures/mock_month
python -m server.tools.make_api_fixtures
```

## Tests run and results (paste the summary lines)
- `scripts\test_a.ps1` → 88 passed, 1 warning in 45.12s
- `pytest --noconftest server/tests/test_api_fixtures.py -q` → 19 passed in 0.65s (B's DB tests not runnable on Laptop A: no psycopg)
- Manual, browser, mock mode: landing, Artists, portal, dashboard at 1440×900 and 375×812; no sideways scroll; no console errors.

## Decisions taken (also appended to DECISIONS.md if they affect the other side)
- Simulated cheating scenarios never use a real artist's song (fictional test tracks); see R-019.

## Contract impact
- none (fixture content changed, schemas unchanged; song IDs unchanged)

## Known issues / risks
- Not tested against B's live server (unreachable since 2026-11-24 12:40).
- B must re-import the mock month (numbers changed) and may regenerate artist_shares.json.
- 13 songs have no cover; artists whose names differ on B show initials.

## Uncommitted or local-only state
- Song packages v1..v3 zips (audio) in Downloads on Laptop A only. B holds the 60 v1 songs; v3 (183 songs) is ready to load.

## Next action (one concrete step the next session does first)
- B: fetch a/work (or the bundle `Fair_Play_a-work.bundle`), merge, re-import the mock month, restart, open `/sonacam-x7k2q9.html`.

## Notes for the other side
- Read R-017, R-018, R-019 in REQUESTS.md. `/` is the public landing now; the dashboard is `/sonacam-x7k2q9.html`.
