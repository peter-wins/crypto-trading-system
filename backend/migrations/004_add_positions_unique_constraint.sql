-- 004_add_positions_unique_constraint.sql
-- 目的: 为 positions 表添加 (exchange_id, symbol, side, is_open) 唯一约束，
--      确保双向持仓在数据库层面不会出现重复记录。

BEGIN;

-- 1. 清理潜在的重复记录，只保留每组最早的一条
WITH ranked_positions AS (
    SELECT
        ctid,
        ROW_NUMBER() OVER (
            PARTITION BY exchange_id, symbol, side, is_open
            ORDER BY id
        ) AS rn
    FROM positions
),
duplicates AS (
    SELECT ctid
    FROM ranked_positions
    WHERE rn > 1
)
DELETE FROM positions
WHERE ctid IN (SELECT ctid FROM duplicates);

-- 2. 添加唯一约束
ALTER TABLE positions
ADD CONSTRAINT uq_positions_exchange_symbol_side_open
UNIQUE (exchange_id, symbol, side, is_open);

COMMIT;

-- 如需回滚:
-- ALTER TABLE positions DROP CONSTRAINT IF EXISTS uq_positions_exchange_symbol_side_open;
