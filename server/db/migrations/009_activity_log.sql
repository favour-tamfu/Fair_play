-- D-024: activity log for SONACAM admins — one organised, persistent record of what the system did
-- (meter reports, songs recognised, plays logged, flags, play-log checks, stats runs, meters on/offline,
-- rejected reports, admin actions). Read through GET /api/v1/admin/activity (admin password).
CREATE TABLE IF NOT EXISTS activity_log (
  id        bigserial PRIMARY KEY,
  at        timestamptz NOT NULL DEFAULT now(),
  kind      text NOT NULL,                 -- report | heard | play | flag | meter | ledger | stats | admin | rejected | catalogue
  level     text NOT NULL DEFAULT 'info',  -- info | warn | error
  meter_id  text,
  venue_id  text,
  song_id   text,
  actor     text,                          -- who did it: a meter id, 'admin', 'scheduler', 'server', an IP for refused admin calls
  message   text NOT NULL,                 -- one line for people
  detail    jsonb
);
CREATE INDEX IF NOT EXISTS activity_log_at ON activity_log (at DESC);
CREATE INDEX IF NOT EXISTS activity_log_kind_id ON activity_log (kind, id DESC);
CREATE INDEX IF NOT EXISTS activity_log_meter_id ON activity_log (meter_id, id DESC);
