-- A new meter asks to join (POST /v1/meters/join, signed with its own key); SONACAM approves or rejects it on the
-- operations page. Until approved the meter is unknown and its reports are refused (404 unknown_meter, kept on the meter).
CREATE TABLE IF NOT EXISTS meter_requests (
    meter_id        text PRIMARY KEY,
    venue_id        text NOT NULL,
    public_key_b64  text NOT NULL,
    created_at      text,
    computer        text,
    status          text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
    requested_at    timestamptz NOT NULL DEFAULT now(),
    last_asked_at   timestamptz NOT NULL DEFAULT now(),
    decided_at      timestamptz,
    decided_by      text
);
CREATE INDEX IF NOT EXISTS meter_requests_status ON meter_requests (status);
