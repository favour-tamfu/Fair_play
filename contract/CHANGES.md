# Contract changes (protocol: docs/02 §6)

## c-1.0 — 2026-11-23 12:00 — initial contract (A+B)
- As written in docs/01_CONTRACT.md. Package/brand renamed to Fair Play before any code existed (DECISIONS D-002); no change of content.
- 2026-11-23 23:10 — B — JSON Schemas written in `contract/schemas/` (draft 2020-12). Clarifications within c-1.0 (no field added, removed or renamed):
  - Extra schema files mirroring existing contract text: `songs.schema.json` (§5 list), `song.schema.json` (§5 detail + owners), `artists.schema.json` (§6 GET /api/v1/artists).
  - All objects are closed (`additionalProperties: false`): a misspelt field fails validation.
  - `null` allowed where data may not exist yet: `overview.last_anchor`, `ledger_status.last_anchor/last_root`, `shares.stats_run_id` (no stats run yet), `plays[].weight` (not weighted yet), `venues[].city/lat/lon/stratum/bars_in_stratum` (live venue known only from a meter key), `venues[].meters[].last_seen`, `songs[].isrc/iswc/duration_s/duplicate_of`, `flags[].song_id/venue_id`.
  - ID patterns: plays `^P-[0-9A-Za-z]{4,32}$` (mock month play_ids must start with `P-`), stats runs `^R-[0-9]{14}$`, songs `S-000001` / `S-M0001`.
- 2026-11-24 01:00 — B — Additive, optional: `GET /api/v1/songs?source=upload|mock|all` (default `upload`: the portal lists uploaded songs only; the mock-month catalogue appears with `mock`/`all`). Upload errors: HTTP 400 `{"error":"invalid_upload","detail":"…"}`.

## c-1.1 (PROPOSED) — 2026-11-24 02:00 — B — Song upload size limit 30 MB → 50 MB
- What: contract §5 `POST /api/v1/songs`: `file … ≤ 30 MB` becomes `≤ 50 MB`.
- Why: a typical full-length studio WAV export (e.g. 3:44, 44.1 kHz stereo) is about 38 MB and was refused. Decided by Person B (human).
- Impact on B: `server/config.py UPLOAD_MAX_BYTES` = 50 MB (already deployed; accepting more is backward compatible).
- Impact on A: portal client-side check (A-T12) 30 → 50 MB, and the portal's error text.
- Status: waiting for ACK from A. After ACK, B updates docs/01_CONTRACT.md §5 and the version becomes c-1.1.
- 2026-11-24 03:20 — B — Additive (no change to existing shapes): `GET /api/v1/ledger/anchors?limit=24` → `[{"hour","root","n_plays","via","tx_ref","created_at"}]` newest first (Trust tab "last anchors"), and `POST /api/v1/ledger/anchor` → anchor the current hour now (`{"ok","hour","root","n_plays","via","tx_ref"}`, or `{"ok":false,"detail"}` if no plays yet). `ledger_status.last_root` = root of the most recent anchor (null before the first anchor).
- 2026-11-24 03:45 — B — Read API semantics (clarifications within c-1.0): before the first stats run `plays[].weight` is null and `overview.plays_counted` = `plays_raw`; `compare-flat` returns `n_artists: 0` (= not computed yet) until the mock month is imported; `payouts.rows` is empty until B-T12 but `frozen` already follows the ledger. Plays superseded by a correction are never listed or counted. `GET /api/v1/artists/{name}` also accepts `period` and `mode`.
- 2026-11-24 04:50 — B — Clarification (no shape change): `plays[].reasons` vocabulary = `streak_1`…`streak_4` | `cooldown` (always first), then optional `loop`, `low_audience`, `concentration`. Per D-009 `loop`, `low_audience` and `concentration` are **review flags only — they do not change `weight`**; only streak/cooldown changes weight. Dashboard wording suggestion: "flagged for SONACAM review". `flags[].type` values unchanged.
- 2026-11-24 05:00 — B — Additive (within c-1.0): `POST /api/v1/stats/run?period=live|mock_month|all&mode=both|standardised|raw` (default `live`, `both`) → `{"stats_run_id","status":"done","duration_ms"}` plus `period, mode, n_plays, n_songs, n_flags` (with `both`: the standardised run's id, `raw_stats_run_id`, total duration). SSE `stats` data = `{"stats_run_id","period","mode"}` (refetch shares only for the period/mode on screen). `GET /api/v1/flags?period=` = flags of that period's latest stats run + catalogue flags (`duplicate_suspected`); the live scheduler refreshes every 5 min.
