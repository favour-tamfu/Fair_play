-- D-029: SONACAM can mark a review flag as reviewed, and retire a meter (its reports are then refused).
ALTER TABLE flags ADD COLUMN IF NOT EXISTS reviewed_at timestamptz;
ALTER TABLE flags ADD COLUMN IF NOT EXISTS reviewed_by text;
ALTER TABLE flags ADD COLUMN IF NOT EXISTS review_note text;
ALTER TABLE meters ADD COLUMN IF NOT EXISTS retired_at timestamptz;
