-- 为 closed_positions 表添加 close_reason 字段
-- 用于记录持仓关闭的原因（手动平仓、止盈止损、强平等）

ALTER TABLE closed_positions
ADD COLUMN IF NOT EXISTS close_reason VARCHAR(50);

-- 添加约束，确保 close_reason 只能是预定义的值
ALTER TABLE closed_positions
ADD CONSTRAINT close_reason_check
CHECK (close_reason IN ('manual', 'stop_loss', 'take_profit', 'liquidation', 'system', 'unknown'));

-- 为现有记录设置默认值
UPDATE closed_positions
SET close_reason = 'unknown'
WHERE close_reason IS NULL;

-- 添加注释
COMMENT ON COLUMN closed_positions.close_reason IS '平仓原因：manual(手动), stop_loss(止损), take_profit(止盈), liquidation(强平), system(系统), unknown(未知)';

-- 创建索引以便按原因查询
CREATE INDEX IF NOT EXISTS idx_closed_positions_close_reason ON closed_positions (close_reason);
