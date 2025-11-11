#!/usr/bin/env python3
"""
数据库迁移脚本 - 添加币安对齐字段
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from sqlalchemy import text
from src.core.config import get_config
from src.database.manager import DatabaseManager
from src.core.logger import get_logger

logger = get_logger(__name__)


async def run_migration():
    """执行数据库迁移"""
    config = get_config()
    db_manager = DatabaseManager(config.database_url)

    try:
        await db_manager.connect()
        logger.info("✅ 数据库连接成功")

        async with db_manager.get_session() as session:
            # 检查表是否存在
            result = await session.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'portfolio_snapshots'
                );
            """))
            table_exists = result.scalar()

            if not table_exists:
                logger.error("❌ 表 portfolio_snapshots 不存在")
                return False

            logger.info("📊 开始迁移...")

            # 添加新字段
            migration_sqls = [
                # 添加新字段
                "ALTER TABLE portfolio_snapshots ADD COLUMN IF NOT EXISTS wallet_balance NUMERIC(20, 8)",
                "ALTER TABLE portfolio_snapshots ADD COLUMN IF NOT EXISTS available_balance NUMERIC(20, 8)",
                "ALTER TABLE portfolio_snapshots ADD COLUMN IF NOT EXISTS margin_balance NUMERIC(20, 8)",
                "ALTER TABLE portfolio_snapshots ADD COLUMN IF NOT EXISTS unrealized_pnl NUMERIC(20, 8)",

                # 修改旧字段为可空
                "ALTER TABLE portfolio_snapshots ALTER COLUMN total_value DROP NOT NULL",
                "ALTER TABLE portfolio_snapshots ALTER COLUMN cash DROP NOT NULL",
            ]

            for sql in migration_sqls:
                try:
                    await session.execute(text(sql))
                    logger.info(f"  ✓ {sql[:50]}...")
                except Exception as e:
                    logger.warning(f"  ⚠ {sql[:50]}... 失败: {e}")

            # 数据迁移：将旧字段数据复制到新字段
            data_migration_sql = """
                UPDATE portfolio_snapshots
                SET
                  wallet_balance = total_value,
                  available_balance = cash,
                  margin_balance = 0,
                  unrealized_pnl = COALESCE(total_pnl, 0)
                WHERE wallet_balance IS NULL
            """
            result = await session.execute(text(data_migration_sql))
            await session.commit()
            logger.info(f"  ✓ 数据迁移完成，更新了 {result.rowcount} 行")

            # 验证迁移
            verify_sql = """
                SELECT
                  COUNT(*) as total_rows,
                  COUNT(wallet_balance) as has_wallet_balance,
                  COUNT(available_balance) as has_available_balance
                FROM portfolio_snapshots
            """
            result = await session.execute(text(verify_sql))
            row = result.fetchone()

            logger.info("\n📊 迁移验证:")
            logger.info(f"  总行数: {row[0]}")
            logger.info(f"  有 wallet_balance: {row[1]}")
            logger.info(f"  有 available_balance: {row[2]}")

            if row[0] > 0 and row[1] == row[0] and row[2] == row[0]:
                logger.info("\n✅ 迁移成功！")
                return True
            elif row[0] == 0:
                logger.info("\n✅ 迁移成功（表为空）")
                return True
            else:
                logger.error("\n❌ 迁移可能不完整")
                return False

    except Exception as e:
        logger.error(f"❌ 迁移失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await db_manager.disconnect()


if __name__ == "__main__":
    print("🔄 数据库迁移工具")
    print("=" * 50)
    success = asyncio.run(run_migration())
    sys.exit(0 if success else 1)
