-- 008_meter_health (B-T14): calibration runs are re-evaluated for a while after receipt; per-play detail kept.
ALTER TABLE calibrations ADD COLUMN IF NOT EXISTS received_at timestamptz NOT NULL DEFAULT now();
ALTER TABLE calibrations ADD COLUMN IF NOT EXISTS updated_at timestamptz;
ALTER TABLE calibrations ADD COLUMN IF NOT EXISTS applied boolean NOT NULL DEFAULT false;
ALTER TABLE calibrations ADD COLUMN IF NOT EXISTS detail jsonb;
CREATE INDEX IF NOT EXISTS flags_meter_type ON flags(meter_id, type);
