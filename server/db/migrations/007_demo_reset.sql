-- 007_demo_reset (B-T13, D-017): demo reset starts a new live-chain epoch.
-- Each reset is recorded; the anchors of the previous epoch are archived (their plays are gone, so the auditor can
-- no longer re-check them), never silently deleted. The public anchors file also gets an "epoch" line.
CREATE TABLE IF NOT EXISTS ledger_epochs (epoch serial PRIMARY KEY, started_at timestamptz NOT NULL DEFAULT now(),
  reason text, plays_removed int NOT NULL DEFAULT 0, last_root text);
CREATE TABLE IF NOT EXISTS anchors_archive (epoch int NOT NULL, hour timestamptz NOT NULL, root text, n_plays int,
  via text, tx_ref text, created_at timestamptz, archived_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (epoch, hour));
