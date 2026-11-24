# Handoff A-WEB — 2026-11-24 23:46 — Person A / Laptop A
Task: A-WEB public site, artist portal, SONACAM dashboard and admin (A-T11..A-T14, A-T17)   Status: PARTIAL (all pages built; not yet run against B)
Contract version in use: c-1.3   fp_version: fp-1.0   Branch: a/work   Last commit: see `git log -1` (this handoff commit)

## What was done (facts only)
- Site map (all under `web/`, B serves the folder at `/`):
  - `index.html` public landing page (no longer the dashboard): photo hero, laptop mockup with a static dashboard screenshot, dark music-product-page sections, numbers, trust chain, how it works, questions.
  - `artist.html` "Artists", the public data pool: finder (`artist.html`) and an artist page (`artist.html?name=`).
  - `portal.html` "Artist portal", private artist space: prototype sign-in by artist name (no password yet, R-018), activity feed, my songs, declare a song (only place to upload).
  - `sonacam-x7k2q9.html` SONACAM dashboard (unlisted address, noindex). Rebuilt: sidebar (views, period, counting, links), filter box, five figure cards, dot-matrix "Plays by artist" chart (one column per song, dark = counted, light = heard; tooltip and table view), who earned what, map, live feed, Songs and Trust views. Apple styling (same values as the landing: #f5f5f7/#fff/#1d1d1f, accent #0071e3, 18px cards).
  - `sonacam-x7k2q9-admin.html` admin (unchanged this session).
- Real album covers: 134 WebP images (1.8 MB) in `web/assets/covers/` with `index.json`; used on the landing, Artists and portal pages. A cover is shown only next to its own artist (namesakes rejected, e.g. "Sabrina Claudio"). Artists without a cover keep their initials.
- Every number shown is computed from the API (or fixtures with `?mock=1`).

## Files created/changed
- web/index.html, web/css/landing.css, web/css/mbp.css (new; laptop mockup adapted from an MIT CodePen, credited in the file), web/js/landing.js
- web/sonacam-x7k2q9.html, web/css/dash.css (new), web/js/app.js
- web/artist.html, web/js/artist.js, web/portal.html, web/js/me.js (new), web/js/portal.js, web/js/site.js (new), web/css/pages.css (new)
- web/js/covers.js (new), web/assets/covers/* (new), web/assets/img/*.webp (photos, credited in the landing footer)

## How to run it (exact commands, PowerShell, from repo root)
```
python -m http.server 8080
# then open http://localhost:8080/web/index.html?mock=1
#           http://localhost:8080/web/sonacam-x7k2q9.html?mock=1&period=mock_month
```
On B: no command; the pages are served from `web/` once B has pulled a/work.

## Tests run and results (paste the summary lines)
- `scripts\test_a.ps1` → 88 passed, 1 warning in 72.38s
- Manual, browser, mock mode: landing, Artists, portal and dashboard at 1440×900 and 375×812; no sideways scroll; chart tooltip, period switch, filter box OK.

## Decisions taken (also appended to DECISIONS.md if they affect the other side)
- `index.html` is the public landing; the dashboard lives at `sonacam-x7k2q9.html` (R-017).
- Album art from the iTunes Search API, stored locally so the demo works offline.

## Contract impact
- none

## Known issues / risks
- Not tested against B's live server (192.168.1.51:8000 unreachable since 12:40). Live SSE, tamper banner and real artist pages need a check on B.
- `web/assets/covers/index.json` keys covers by artist name and title as in the catalogue; artists on B with different spellings show initials.
- The headline font on the original design (SF Pro Plus Expanded) is not installed; SF Pro Heavy is used.
- About 32 catalogue songs still have no cover; a research pass is running and may add a follow-up commit.

## Uncommitted or local-only state
- reports/ and research_notes/ (SONACAM research), untracked on purpose.
- Song packages v1..v3 zips in Downloads on Laptop A only (audio, never committed).

## Next action (one concrete step the next session does first)
- B: `git fetch` and merge a/work (or receive the bundle), restart the server, open `http://192.168.1.51:8000/sonacam-x7k2q9.html` and check live plays reach the chart, map and feed.

## Notes for the other side
- B: pages changed address (R-017) and the portal sign-in is a prototype (R-018). The landing links to `artist.html` and `portal.html`; the dashboard is reachable only by its address.
- B currently holds the 60 v1 songs; the v3 package (183 songs) is ready on Laptop A.
