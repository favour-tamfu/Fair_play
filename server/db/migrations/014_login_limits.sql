-- Sign-in limits (server/login_guard.py): failed sign-ins per account, per internet address and for all artists.
CREATE TABLE IF NOT EXISTS login_failures (
    id   bigserial PRIMARY KEY,
    key  text NOT NULL,
    at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS login_failures_key_at ON login_failures (key, at);
