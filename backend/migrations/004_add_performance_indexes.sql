-- Migration: 004_add_performance_indexes
-- Description: 为绩效相关表添加索引以提升查询性能
-- Created: 2025-11-18

-- 为 portfolio_snapshots 表添加复合索引
-- 用于优化按交易所和日期范围查询快照
CREATE INDEX IF NOT EXISTS idx_portfolio_snapshots_exchange_date
ON portfolio_snapshots(exchange_id, snapshot_date DESC);

CREATE INDEX IF NOT EXISTS idx_portfolio_snapshots_datetime
ON portfolio_snapshots(datetime DESC);

-- 为 closed_positions 表添加索引
-- 用于优化按交易所、日期范围查询已平仓记录
CREATE INDEX IF NOT EXISTS idx_closed_positions_exchange_exit_time
ON closed_positions(exchange_id, exit_time DESC);

CREATE INDEX IF NOT EXISTS idx_closed_positions_symbol_exit_time
ON closed_positions(symbol, exit_time DESC);

-- 为 performance_metrics 表添加索引
-- 用于优化按日期范围查询绩效指标
CREATE INDEX IF NOT EXISTS idx_performance_metrics_date_range
ON performance_metrics(start_date DESC, end_date DESC);

-- 为 account_settings 表添加索引（如果还没有）
-- 用于快速查询初始资金配置
CREATE INDEX IF NOT EXISTS idx_account_settings_exchange
ON account_settings(exchange_id);

-- 验证索引创建
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE tablename IN ('portfolio_snapshots', 'closed_positions', 'performance_metrics', 'account_settings')
ORDER BY tablename, indexname;
