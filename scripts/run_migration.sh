#!/bin/bash
# 数据库迁移脚本
# 用法: ./scripts/run_migration.sh

set -e

# 读取环境变量
source ../.env 2>/dev/null || true

# 从 DATABASE_URL 提取连接信息
# 格式: postgresql://user:password@host:port/database
if [ -z "$DATABASE_URL" ]; then
    echo "❌ 错误: DATABASE_URL 未设置"
    exit 1
fi

echo "📊 开始数据库迁移..."
echo "数据库: $DATABASE_URL"
echo ""

# 执行迁移
MIGRATION_FILE="migrations/001_add_binance_fields.sql"

if [ ! -f "$MIGRATION_FILE" ]; then
    echo "❌ 迁移文件不存在: $MIGRATION_FILE"
    exit 1
fi

echo "执行迁移: $MIGRATION_FILE"
psql "$DATABASE_URL" -f "$MIGRATION_FILE"

echo ""
echo "✅ 迁移完成！"
echo ""
echo "📝 新增字段:"
echo "  - wallet_balance (钱包余额)"
echo "  - available_balance (可用保证金)"
echo "  - margin_balance (保证金余额)"
echo "  - unrealized_pnl (未实现盈亏)"
