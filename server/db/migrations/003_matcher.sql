-- 003_matcher (B-T05): one match verdict per received batch (retried jobs can't double-count);
-- fast per-meter, event-time ordered reads for the play logger (B-T06).
CREATE UNIQUE INDEX match_events_raw_batch ON match_events(raw_batch_id);
CREATE INDEX match_events_meter_time ON match_events(meter_id, window_start);
