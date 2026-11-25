-- One request per computer: the meter sends a device id (hash of the computer's machine id, signed with the request).
-- A newer request from the same computer replaces its older waiting one; a computer that already is an active meter
-- cannot ask again until SONACAM retires that meter.
ALTER TABLE meter_requests ADD COLUMN IF NOT EXISTS device_id text;
CREATE INDEX IF NOT EXISTS meter_requests_device ON meter_requests (device_id);
