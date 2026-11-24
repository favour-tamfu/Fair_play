-- 006_mock_month (B-T11, D-013): mock month import.
-- Ledger chain namespace: live plays and mock plays are two separate hash chains; the live chain is never wiped,
-- the mock chain is rebuilt on every re-import. Anchors are for the live chain only.
ALTER TABLE plays ADD COLUMN IF NOT EXISTS chain text NOT NULL DEFAULT 'live';
ALTER TABLE anchors ADD COLUMN IF NOT EXISTS chain text NOT NULL DEFAULT 'live';
CREATE INDEX IF NOT EXISTS plays_chain_seq ON plays(chain, seq_no);

-- The 30 mock meters as A generated them (catch_rate_true = a calibrated meter). Separate from `meters` because
-- the mock IDs M-12/M-13 are also A's real virtual meters at other venues (keys, last_seq): those rows stay as is.
CREATE TABLE IF NOT EXISTS mock_meters (meter_id text PRIMARY KEY, venue_id text NOT NULL, catch_rate double precision,
  installed_at timestamptz);

-- windows_observed.csv comes as 10-minute slot aggregates: stored as they are (not expanded to 10 s windows).
CREATE TABLE IF NOT EXISTS window_slots (meter_id text NOT NULL, slot_start timestamptz NOT NULL, slot_minutes int NOT NULL,
  windows_received int NOT NULL, windows_expected int NOT NULL, mean_loudness_db double precision,
  PRIMARY KEY (meter_id, slot_start));

-- plays_true.csv: what really played in the mock world (ground truth for compare-flat only; never counted).
CREATE TABLE IF NOT EXISTS mock_truth (true_play_id text PRIMARY KEY, venue_id text, song_id text, started_at timestamptz,
  duration_s double precision, scenario text);
CREATE INDEX IF NOT EXISTS mock_truth_song ON mock_truth(song_id);
