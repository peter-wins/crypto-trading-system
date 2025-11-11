-- 添加币安对齐的字段到 portfolio_snapshots 表
-- 迁移脚本: 001_add_binance_fields.sql
-- 日期: 2025-11-10

-- 添加新字段（与币安命名对齐）
ALTER TABLE portfolio_snapshots
ADD COLUMN IF NOT EXISTS wallet_balance NUMERIC(20, 8),
ADD COLUMN IF NOT EXISTS available_balance NUMERIC(20, 8),
ADD COLUMN IF NOT EXISTS margin_balance NUMERIC(20, 8),
ADD COLUMN IF NOT EXISTS unrealized_pnl NUMERIC(20, 8);

-- 修改旧字段为可空（兼容性）
ALTER TABLE portfolio_snapshots
ALTER COLUMN total_value DROP NOT NULL,
ALTER COLUMN cash DROP NOT NULL;

-- 数据迁移：将旧字段数据复制到新字段
UPDATE portfolio_snapshots
SET
  wallet_balance = total_value,
  available_balance = cash,
  margin_balance = 0,
  unrealized_pnl = COALESCE(total_pnl, 0)
WHERE wallet_balance IS NULL;

-- 添加注释
COMMENT ON COLUMN portfolio_snapshots.wallet_balance IS '钱包余额 Wallet Balance（总资金）';
COMMENT ON COLUMN portfolio_snapshots.available_balance IS '可用保证金 Available Balance';
COMMENT ON COLUMN portfolio_snapshots.margin_balance IS '保证金余额 Margin Balance（持仓占用）';
COMMENT ON COLUMN portfolio_snapshots.unrealized_pnl IS '未实现盈亏 Unrealized PNL';

-- 验证迁移
SELECT
  COUNT(*) as total_rows,
  COUNT(wallet_balance) as has_wallet_balance,
  COUNT(available_balance) as has_available_balance
FROM portfolio_snapshots;
