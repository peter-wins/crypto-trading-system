BEGIN;

ALTER TABLE positions
ADD COLUMN IF NOT EXISTS entry_fee NUMERIC(20, 8) DEFAULT 0;

UPDATE positions
SET entry_fee = COALESCE(entry_fee, 0);

COMMIT;
