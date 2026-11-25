-- D-028: role-based access. Two roles: 'sonacam' (SONACAM staff and admins: everything) and 'artist' (own songs only).
CREATE TABLE IF NOT EXISTS users (
  username      text PRIMARY KEY,               -- lower-case login name (the artist name for artists)
  display_name  text NOT NULL,
  role          text NOT NULL CHECK (role IN ('sonacam', 'artist')),
  artist_name   text,                            -- for role 'artist': exactly songs.artist_name
  password_hash text NOT NULL,                   -- scrypt$<salt hex>$<hash hex>
  created_at    timestamptz NOT NULL DEFAULT now(),
  last_login    timestamptz
);
CREATE TABLE IF NOT EXISTS sessions (
  token_hash  text PRIMARY KEY,                  -- sha256 of the cookie value (the cookie itself is never stored)
  username    text NOT NULL REFERENCES users (username) ON DELETE CASCADE,
  created_at  timestamptz NOT NULL DEFAULT now(),
  expires_at  timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS sessions_expires ON sessions (expires_at);
