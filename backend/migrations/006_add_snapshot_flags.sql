BEGIN;

ALTER TABLE portfolio_snapshots
ADD COLUMN IF NOT EXISTS archive_reason VARCHAR(50),
ADD COLUMN IF NOT EXISTS is_archive BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS position_count INTEGER DEFAULT 0;

UPDATE portfolio_snapshots
SET is_archive = FALSE,
    archive_reason = COALESCE(archive_reason, 'auto');

COMMIT;
