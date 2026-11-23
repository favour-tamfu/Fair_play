-- 001_init: initial schema (PLAN_B B-T02). Raw tables are append-only (docs/00 §4 principle 2).
CREATE TABLE venues (venue_id text PRIMARY KEY, name text, city text, lat double precision, lon double precision,
  size_class text, stratum text, bars_in_stratum int, open_hour int DEFAULT 18, close_hour int DEFAULT 2, source text DEFAULT 'live');
CREATE TABLE meters (meter_id text PRIMARY KEY, venue_id text REFERENCES venues, public_key_b64 text NOT NULL,
  last_seq bigint DEFAULT 0, last_seen timestamptz, queued int DEFAULT 0, cell_id text, catch_rate double precision DEFAULT 0.8,
  clock_skew_s double precision, source text DEFAULT 'live');
CREATE TABLE songs (song_id text PRIMARY KEY, title text, artist_name text, isrc text, iswc text, duration_s double precision,
  status text, n_hashes int DEFAULT 0, file_path text, uploaded_at timestamptz DEFAULT now(), duplicate_of text, source text DEFAULT 'upload');
CREATE TABLE owners (id bigserial PRIMARY KEY, song_id text REFERENCES songs, owner_name text, role text, share_pct double precision, momo text);
CREATE TABLE fp_hashes (hash int NOT NULL, song_id text NOT NULL, t int NOT NULL);
CREATE INDEX fp_hashes_hash ON fp_hashes(hash);
CREATE TABLE raw_batches (id bigserial PRIMARY KEY, meter_id text, venue_id text, seq bigint, window_start timestamptz,
  received_at timestamptz DEFAULT now(), body jsonb, late boolean DEFAULT false, processed boolean DEFAULT false,
  UNIQUE(meter_id, seq));
CREATE TABLE match_events (id bigserial PRIMARY KEY, raw_batch_id bigint REFERENCES raw_batches, meter_id text, venue_id text,
  window_start timestamptz, song_id text, offset_s double precision, best_score int, second_score int, confidence double precision,
  accepted boolean, loudness_db double precision, created_at timestamptz DEFAULT now());
CREATE TABLE plays (play_id text PRIMARY KEY, meter_id text, venue_id text, song_id text, started_at timestamptz,
  ended_at timestamptz, duration_s double precision, first_offset_s double precision, n_windows int, loudness_db double precision,
  source text, prev_chain_hash text, chain_hash text, inserted_at timestamptz DEFAULT now(), seq_no bigserial UNIQUE);
CREATE TABLE play_corrections (id bigserial PRIMARY KEY, play_id text, reason text, detail jsonb, created_at timestamptz DEFAULT now());
CREATE TABLE play_weights (play_id text, rule_version text, stats_run_id text, weight double precision, reasons text[],
  PRIMARY KEY (play_id, stats_run_id));
CREATE TABLE stats_runs (stats_run_id text PRIMARY KEY, period text, mode text, rule_version text, started_at timestamptz,
  finished_at timestamptz, params jsonb);
CREATE TABLE shares (stats_run_id text, song_id text, raw_plays int, weighted_plays double precision, share double precision,
  ci_low double precision, ci_high double precision, flags text[], PRIMARY KEY (stats_run_id, song_id));
CREATE TABLE flags (flag_id bigserial PRIMARY KEY, type text, song_id text, venue_id text, meter_id text, detail text,
  created_at timestamptz DEFAULT now(), stats_run_id text);
CREATE TABLE anchors (hour timestamptz PRIMARY KEY, root text, n_plays int, via text, tx_ref text, created_at timestamptz DEFAULT now());
CREATE TABLE calibrations (run_id text PRIMARY KEY, meter_id text, started_at timestamptz, ended_at timestamptz,
  expected jsonb, matched int, total int, catch_rate double precision);
CREATE TABLE payouts (stats_run_id text, owner_name text, role text, song_id text, amount_fcfa bigint, momo text, status text);
CREATE TABLE jobs (id bigserial PRIMARY KEY, kind text, ref text, status text DEFAULT 'queued', attempts int DEFAULT 0,
  error text, created_at timestamptz DEFAULT now(), updated_at timestamptz DEFAULT now());
CREATE TABLE windows (meter_id text, window_start timestamptz, loudness_db double precision, received boolean, source text,
  PRIMARY KEY (meter_id, window_start));
-- job board: fast lookup of queued jobs per kind
CREATE INDEX jobs_queued ON jobs(kind, id) WHERE status = 'queued';
