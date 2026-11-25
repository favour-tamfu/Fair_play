# Contract changes (protocol: docs/02 §6)

## c-1.0 — 2026-11-23 12:00 — initial contract (A+B)
- As written in docs/01_CONTRACT.md. Package/brand renamed to Fair Play before any code existed (DECISIONS D-002); no change of content.
- 2026-11-23 23:10 — B — JSON Schemas written in `contract/schemas/` (draft 2020-12). Clarifications within c-1.0 (no field added, removed or renamed):
  - Extra schema files mirroring existing contract text: `songs.schema.json` (§5 list), `song.schema.json` (§5 detail + owners), `artists.schema.json` (§6 GET /api/v1/artists).
  - All objects are closed (`additionalProperties: false`): a misspelt field fails validation.
  - `null` allowed where data may not exist yet: `overview.last_anchor`, `ledger_status.last_anchor/last_root`, `shares.stats_run_id` (no stats run yet), `plays[].weight` (not weighted yet), `venues[].city/lat/lon/stratum/bars_in_stratum` (live venue known only from a meter key), `venues[].meters[].last_seen`, `songs[].isrc/iswc/duration_s/duplicate_of`, `flags[].song_id/venue_id`.
  - ID patterns: plays `^P-[0-9A-Za-z]{4,32}$` (mock month play_ids must start with `P-`), stats runs `^R-[0-9]{14}$`, songs `S-000001` / `S-M0001`.
- 2026-11-24 01:00 — B — Additive, optional: `GET /api/v1/songs?source=upload|mock|all` (default `upload`: the portal lists uploaded songs only; the mock-month catalogue appears with `mock`/`all`). Upload errors: HTTP 400 `{"error":"invalid_upload","detail":"…"}`.

## c-1.1 (ACCEPTED 2026-11-24 06:50, ACK A 05:18) — 2026-11-24 02:00 — B — Song upload size limit 30 MB → 50 MB
- What: contract §5 `POST /api/v1/songs`: `file … ≤ 30 MB` becomes `≤ 50 MB`.
- Why: a typical full-length studio WAV export (e.g. 3:44, 44.1 kHz stereo) is about 38 MB and was refused. Decided by Person B (human).
- Impact on B: `server/config.py UPLOAD_MAX_BYTES` = 50 MB (already deployed; accepting more is backward compatible).
- Impact on A: portal client-side check (A-T12) 30 → 50 MB, and the portal's error text.
- Status: ACK by A 2026-11-24 05:18 (below). docs/01_CONTRACT.md §5 updated, version is now c-1.1 (MC1 merge).
- 2026-11-24 03:20 — B — Additive (no change to existing shapes): `GET /api/v1/ledger/anchors?limit=24` → `[{"hour","root","n_plays","via","tx_ref","created_at"}]` newest first (Trust tab "last anchors"), and `POST /api/v1/ledger/anchor` → anchor the current hour now (`{"ok","hour","root","n_plays","via","tx_ref"}`, or `{"ok":false,"detail"}` if no plays yet). `ledger_status.last_root` = root of the most recent anchor (null before the first anchor).
- 2026-11-24 03:45 — B — Read API semantics (clarifications within c-1.0): before the first stats run `plays[].weight` is null and `overview.plays_counted` = `plays_raw`; `compare-flat` returns `n_artists: 0` (= not computed yet) until the mock month is imported; `payouts.rows` is empty until B-T12 but `frozen` already follows the ledger. Plays superseded by a correction are never listed or counted. `GET /api/v1/artists/{name}` also accepts `period` and `mode`.
- 2026-11-24 04:50 — B — Clarification (no shape change): `plays[].reasons` vocabulary = `streak_1`…`streak_4` | `cooldown` (always first), then optional `loop`, `low_audience`, `concentration`. Per D-009 `loop`, `low_audience` and `concentration` are **review flags only — they do not change `weight`**; only streak/cooldown changes weight. Dashboard wording suggestion: "flagged for SONACAM review". `flags[].type` values unchanged.
- 2026-11-24 05:00 — B — Additive (within c-1.0): `POST /api/v1/stats/run?period=live|mock_month|all&mode=both|standardised|raw` (default `live`, `both`) → `{"stats_run_id","status":"done","duration_ms"}` plus `period, mode, n_plays, n_songs, n_flags` (with `both`: the standardised run's id, `raw_stats_run_id`, total duration). SSE `stats` data = `{"stats_run_id","period","mode"}` (refetch shares only for the period/mode on screen). `GET /api/v1/flags?period=` = flags of that period's latest stats run + catalogue flags (`duplicate_suspected`); the live scheduler refreshes every 5 min.
- 2026-11-24 05:40 — B — Semantics per D-011 (no shape change): `shares.rows[].ci_low` = `ci_high` = `share` (full coverage, no sampling range); `shares.escrow_share` = 0 and `overview.unidentified_music_min` = 0 always (unidentified music is not recorded). `venues[].stratum/bars_in_stratum` are descriptive only. Fixtures `contract/fixtures/api/overview.json`, `shares_raw.json`, `shares_standardised.json` regenerated accordingly.

- 2026-11-24 05:18 — A — ACK c-1.1 (upload limit 30 MB -> 50 MB). A-T12 portal will check 50 MB and show the new error text. No objection. Meter path (batches) is not affected.

## c-1.2 (PROPOSED) — 2026-11-24 10:03 — A — Period status on shares and payouts
- What: add `period_status` (`open` | `closed`) and `closed_at` (UTC time or null) to `GET /api/v1/shares` and `GET /api/v1/payouts`.
- Why: money should only be shown once a period's statistics are final. While a period is open, shares can still change, so the web shows shares only and says the amounts come at period close.
- Impact on B: report whether the stats run's period is closed; payouts would only be generated for closed periods.
- Impact on A: the dashboard and artist page read `period_status` instead of assuming `live` is open and `mock_month` is closed (current temporary rule in web/js/app.js and web/js/artist.js).
- Status: NOT ADOPTED (B, 2026-11-24 11:05): superseded by D-015 — Person B decided this version shows no money at all (artists' cumulative shares only), so no period status is needed. See c-1.3.

## c-1.3 — 2026-11-24 10:50 — PROPOSED (B) — artists earn a cumulative share; no money (D-015)
- Additive: `GET /api/v1/artist-shares?period=&mode=` → `{"period","mode","stats_run_id","rule_version","frozen","rules":[str],"rows":[{"rank","artist_name","share","n_songs","raw_plays","counted_plays","songs":[{"song_id","title","share","raw_plays","counted_plays"}]}]}` (`artist_shares.schema.json`, fixture `artist_shares.json`). An artist's share = sum of their songs' shares; rows sum to 1; `frozen=true` (ledger not intact) → `rows` empty. `rules` = plain-language rule text for the page.
- Additive: `GET /api/v1/artists/{name}` gets `share` (the artist's cumulative share).
- Additive: `GET /api/v1/export/usage_report.csv?period=&mode=` — usage report (prototype), shares only (columns `song_id,isrc,iswc,title,artist_name,period_start,period_end,raw_plays,counted_plays,share,artist_share,rule_version,stats_run_id`).
- Deprecated (kept so no page breaks; pages should stop showing them): `amount_fcfa` in `shares.rows`, `artist`, and the `payouts` endpoint. This version ends at what each artist truly earned (the share); paying it out is not modelled.
- Status: waiting for A's ACK (R-011). Web pages updated by B with Person B's approval while A was offline (R-015).
- 2026-11-24 12:35 — B — Additive (with c-1.3): `POST /v1/calibration` answers `{"ok":true,"run_id","matched","total","catch_rate","applied","pending_windows"}` (window ±60 s as in §4). Flags `clock_skew` and `meter_moved` are now produced (types already in §6): `detail` is plain text for people, `venue_id` set, `song_id` null.

## c-1.4 — 2026-11-25 03:00 — PROPOSED (B, Person B asked for the landing page to show live and monthly data) — plays per bar
- Additive, optional for readers: each `GET /api/v1/venues` item gets `source` (`live` | `virtual` | `mock`) and `plays` = `{"live": int, "mock_month": int}` (recorded plays at that bar per period). `venues.schema.json` updated (both fields optional, so old fixtures stay valid).
- Used by the landing page map (bar size = plays in the selected period). No existing field changes.
- Status: waiting for A's ACK.

