-- Migration: 005_fix_holding_duration
-- Description: 添加持仓时间非负约束，防止未来出现负数
-- Created: 2025-11-18

-- 1. 添加检查约束：持仓时间必须非负（允许NULL）
ALTER TABLE closed_positions
ADD CONSTRAINT chk_holding_duration_non_negative
CHECK (holding_duration_seconds IS NULL OR holding_duration_seconds >= 0);

-- 2. 添加检查约束：exit_time 必须晚于或等于 entry_time
ALTER TABLE closed_positions
ADD CONSTRAINT chk_exit_after_entry
CHECK (exit_time >= entry_time);

-- 3. 验证约束
SELECT
    conname as constraint_name,
    contype as constraint_type,
    pg_get_constraintdef(oid) as constraint_definition
FROM pg_constraint
WHERE conrelid = 'closed_positions'::regclass
  AND conname LIKE 'chk_%'
ORDER BY conname;

-- 4. 验证数据
SELECT
    COUNT(*) as total_records,
    COUNT(CASE WHEN holding_duration_seconds < 0 THEN 1 END) as negative_duration,
    COUNT(CASE WHEN exit_time < entry_time THEN 1 END) as invalid_time_order,
    MIN(holding_duration_seconds) as min_duration,
    MAX(holding_duration_seconds) as max_duration
FROM closed_positions;
