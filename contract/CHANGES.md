# Contract changes (protocol: docs/02 §6)

## c-1.0 — 2026-11-23 12:00 — initial contract (A+B)
- As written in docs/01_CONTRACT.md. Package/brand renamed to Fair Play before any code existed (DECISIONS D-002); no change of content.
- 2026-11-23 23:10 — B — JSON Schemas written in `contract/schemas/` (draft 2020-12). Clarifications within c-1.0 (no field added, removed or renamed):
  - Extra schema files mirroring existing contract text: `songs.schema.json` (§5 list), `song.schema.json` (§5 detail + owners), `artists.schema.json` (§6 GET /api/v1/artists).
  - All objects are closed (`additionalProperties: false`): a misspelt field fails validation.
  - `null` allowed where data may not exist yet: `overview.last_anchor`, `ledger_status.last_anchor/last_root`, `shares.stats_run_id` (no stats run yet), `plays[].weight` (not weighted yet), `venues[].city/lat/lon/stratum/bars_in_stratum` (live venue known only from a meter key), `venues[].meters[].last_seen`, `songs[].isrc/iswc/duration_s/duplicate_of`, `flags[].song_id/venue_id`.
  - ID patterns: plays `^P-[0-9A-Za-z]{4,32}$` (mock month play_ids must start with `P-`), stats runs `^R-[0-9]{14}$`, songs `S-000001` / `S-M0001`.
- 2026-11-24 01:00 — B — Additive, optional: `GET /api/v1/songs?source=upload|mock|all` (default `upload`: the portal lists uploaded songs only; the mock-month catalogue appears with `mock`/`all`). Upload errors: HTTP 400 `{"error":"invalid_upload","detail":"…"}`.

- 2026-11-24 05:18 — A — ACK c-1.1 (upload limit 30 MB -> 50 MB). A-T12 portal will check 50 MB and show the new error text. No objection. Meter path (batches) is not affected.

## c-1.2 (PROPOSED) — 2026-11-24 10:03 — A — Period status on shares and payouts
- What: add `period_status` (`open` | `closed`) and `closed_at` (UTC time or null) to `GET /api/v1/shares` and `GET /api/v1/payouts`.
- Why: money should only be shown once a period's statistics are final. While a period is open, shares can still change, so the web shows shares only and says the amounts come at period close.
- Impact on B: report whether the stats run's period is closed; payouts would only be generated for closed periods.
- Impact on A: the dashboard and artist page read `period_status` instead of assuming `live` is open and `mock_month` is closed (current temporary rule in web/js/app.js and web/js/artist.js).
- Status: waiting for ACK from B.
