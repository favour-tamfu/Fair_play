-- 004_playlogger (B-T06)
-- Plays are immutable and hash-chained at confirmation. What keeps changing while a song is still playing
-- (end time, windows, duration, loudness) lives in play_extents, which is NOT part of the chain.
CREATE TABLE playlogger_state (meter_id text PRIMARY KEY, last_event_id bigint NOT NULL DEFAULT 0,
  last_window_start timestamptz, updated_at timestamptz DEFAULT now());
CREATE TABLE play_extents (play_id text PRIMARY KEY REFERENCES plays, ended_at timestamptz, n_windows int,
  duration_s double precision, loudness_db double precision, venue_day date, updated_at timestamptz DEFAULT now());
-- "music, unidentified" seconds per meter and venue-day (escrow, brief §6); recomputed, so it is a replaceable value
CREATE TABLE unidentified (meter_id text, day date, seconds double precision, PRIMARY KEY (meter_id, day));
CREATE INDEX plays_meter_started ON plays(meter_id, started_at);
CREATE INDEX play_corrections_play ON play_corrections(play_id);
