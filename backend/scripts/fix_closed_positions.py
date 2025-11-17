#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复历史平仓记录中的错误价格

问题：部分平仓记录使用了预登记的估计价格，而非实际成交价
解决：从交易所成交记录中提取实际平均成交价，更新数据库
"""

import asyncio
import sys
from pathlib import Path
from decimal import Decimal
from datetime import datetime, timezone

# 添加项目根目录到 Python 路径
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from src.core.config import Config
from src.core.logger import get_logger
from src.services.database import DatabaseManager, TradingDAO
from src.services.exchange import get_exchange_service

logger = get_logger(__name__)


async def fix_closed_positions(dry_run: bool = True):
    """修复所有平仓记录的价格

    Args:
        dry_run: True=只检查不修改, False=实际修改数据库
    """

    print("正在初始化配置和服务...")

    # 初始化配置和服务
    config = Config()
    print(f"数据库URL: {config.database_url}")
    db_manager = DatabaseManager(config.database_url)

    # 获取交易所服务（全局单例）
    print("获取交易所服务...")
    exchange_service = get_exchange_service()

    # 获取交易所配置用于判断 testnet
    print("获取交易所配置...")
    exchange_config = config.get_exchange_config("binance")
    print(f"交易所: {exchange_config.name}, Testnet: {exchange_config.testnet}")

    try:
        print("连接数据库...")
        async with db_manager.get_session() as session:
            dao = TradingDAO(session)

            # 获取所有平仓记录（按时间倒序，最近的优先）
            from sqlalchemy import text
            query = text("""
                SELECT cp.id, cp.symbol, cp.side, cp.entry_price, cp.exit_price, cp.exit_time,
                       cp.amount, cp.realized_pnl, cp.exit_order_id, cp.close_reason, cp.total_fee,
                       e.name as exchange
                FROM closed_positions cp
                JOIN exchanges e ON cp.exchange_id = e.id
                WHERE e.name = :exchange
                ORDER BY cp.exit_time DESC
                LIMIT 100
            """)
            print("查询平仓记录...")
            # 币安U本位合约的交易所名称是 binanceusdm
            exchange_name = "binanceusdm"
            print(f"使用交易所名称: {exchange_name}")
            result = await session.execute(
                query,
                {"exchange": exchange_name}
            )
            closed_positions = result.fetchall()

            print(f"找到 {len(closed_positions)} 条平仓记录")
            logger.info(f"找到 {len(closed_positions)} 条平仓记录")

            fixed_count = 0
            skipped_count = 0
            error_count = 0

            print(f"\n开始检查 {len(closed_positions)} 条记录...")

            for idx, pos in enumerate(closed_positions, 1):
                print(f"\n[{idx}/{len(closed_positions)}] 处理中...")
                try:
                    print(f"检查: {pos.symbol} {pos.side} 平仓于 {pos.exit_time}")
                    print(f"  当前记录: 开仓价={pos.entry_price}, 平仓价={pos.exit_price}, PNL={pos.realized_pnl}")
                    logger.info(f"\n检查: {pos.symbol} {pos.side} 平仓于 {pos.exit_time}")
                    logger.info(f"  当前记录: 开仓价={pos.entry_price}, 平仓价={pos.exit_price}, PNL={pos.realized_pnl}")

                    # 从交易所获取该时间段的成交记录
                    print("  获取成交记录...")
                    exit_time = pos.exit_time
                    if exit_time.tzinfo is None:
                        exit_time = exit_time.replace(tzinfo=timezone.utc)

                    # 查询平仓前后30分钟的成交记录
                    since_ms = int((exit_time.timestamp() - 1800) * 1000)  # 前30分钟

                    try:
                        trades = await exchange_service.fetch_my_trades(
                            symbol=pos.symbol,
                            since=since_ms,
                            limit=100
                        )
                    except Exception as e:
                        logger.warning(f"  获取成交记录失败: {e}")
                        error_count += 1
                        continue

                    if not trades:
                        logger.warning(f"  未找到成交记录，跳过")
                        skipped_count += 1
                        continue

                    # 筛选平仓交易（买入持仓用sell平，卖出持仓用buy平）
                    close_side = 'sell' if pos.side == 'buy' else 'buy'
                    close_trades = []
                    total_amount = Decimal('0')
                    total_value = Decimal('0')
                    total_fee = Decimal('0')

                    for trade in trades:
                        trade_time = datetime.fromtimestamp(
                            trade.get('timestamp', 0) / 1000,
                            tz=timezone.utc
                        )
                        trade_side = (trade.get('side') or '').lower()

                        # 只看平仓方向的交易
                        if trade_side != close_side:
                            continue

                        # 只看平仓时间附近的交易（前后10分钟）
                        time_diff = abs((trade_time - exit_time).total_seconds())
                        if time_diff > 600:  # 10分钟
                            continue

                        amount = Decimal(str(trade.get('amount', 0)))
                        price = Decimal(str(trade.get('price', 0)))
                        fee = Decimal(str(trade.get('fee', {}).get('cost', 0) or 0))

                        if amount <= 0:
                            continue

                        close_trades.append(trade)
                        total_amount += amount
                        total_value += amount * price
                        total_fee += fee

                    if not close_trades or total_amount <= Decimal('0'):
                        logger.warning(f"  未找到有效的平仓交易，跳过")
                        skipped_count += 1
                        continue

                    # 计算实际平均成交价
                    actual_exit_price = total_value / total_amount

                    # 检查价格差异
                    current_exit_price = Decimal(str(pos.exit_price))
                    price_diff = abs(actual_exit_price - current_exit_price)
                    price_diff_pct = (price_diff / current_exit_price * 100) if current_exit_price > 0 else 0

                    logger.info(f"  实际成交: {len(close_trades)} 笔, 总量={total_amount}, 均价={actual_exit_price:.2f}")
                    logger.info(f"  价格差异: {price_diff:.2f} ({price_diff_pct:.2f}%)")

                    # 如果价格差异小于0.1%，跳过
                    if price_diff_pct < 0.1:
                        logger.info(f"  价格差异很小，无需修复")
                        skipped_count += 1
                        continue

                    # 重新计算 PNL
                    entry_price = Decimal(str(pos.entry_price))
                    amount = Decimal(str(pos.amount))

                    if pos.side == 'buy':
                        # 做多: PNL = (平仓价 - 开仓价) * 数量 - 手续费
                        new_pnl = (actual_exit_price - entry_price) * amount - total_fee
                    else:
                        # 做空: PNL = (开仓价 - 平仓价) * 数量 - 手续费
                        new_pnl = (entry_price - actual_exit_price) * amount - total_fee

                    old_pnl = Decimal(str(pos.realized_pnl))
                    pnl_diff = new_pnl - old_pnl

                    logger.info(f"  PNL变化: {old_pnl:.2f} -> {new_pnl:.2f} (差异: {pnl_diff:+.2f})")

                    # 更新数据库
                    if not dry_run:
                        from sqlalchemy import text
                        update_query = text("""
                            UPDATE closed_positions
                            SET exit_price = :exit_price,
                                realized_pnl = :realized_pnl,
                                total_fee = :total_fee
                            WHERE id = :id
                        """)
                        await session.execute(
                            update_query,
                            {
                                "exit_price": float(actual_exit_price),
                                "realized_pnl": float(new_pnl),
                                "total_fee": float(total_fee),
                                "id": pos.id
                            }
                        )
                        await session.commit()
                        logger.info(f"  ✅ 已修复")
                    else:
                        logger.info(f"  🔍 [DRY-RUN] 将会修复此记录")

                    fixed_count += 1

                except Exception as e:
                    logger.error(f"  ❌ 处理失败: {e}", exc_info=True)
                    error_count += 1
                    continue

            logger.info(f"\n" + "=" * 60)
            if dry_run:
                logger.info(f"DRY-RUN 模式完成 (未实际修改数据库):")
            else:
                logger.info(f"修复完成:")
            logger.info(f"  需要修复: {fixed_count} 条")
            logger.info(f"  跳过: {skipped_count} 条")
            logger.info(f"  错误: {error_count} 条")
            if dry_run and fixed_count > 0:
                logger.info(f"\n如需实际修复，请运行: python scripts/fix_closed_positions.py --apply")
            logger.info("=" * 60)

    finally:
        await db_manager.close()


if __name__ == "__main__":
    import argparse
    import traceback

    parser = argparse.ArgumentParser(description="修复历史平仓记录中的错误价格")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="实际修改数据库（默认只检查不修改）"
    )
    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("修复历史平仓记录中的错误价格")
    print("=" * 60)

    if args.apply:
        print("\n警告: 将会实际修改数据库中的平仓记录")
        print("建议先备份数据库！\n")
        confirm = input("确认继续? (yes/no): ")
        if confirm.lower() != 'yes':
            print("已取消")
            sys.exit(0)
    else:
        print("\nDRY-RUN 模式: 只检查不修改")
        print("使用 --apply 参数来实际修改数据库\n")

    try:
        asyncio.run(fix_closed_positions(dry_run=not args.apply))
    except Exception as e:
        print(f"\n❌ 脚本执行失败: {e}")
        traceback.print_exc()
        sys.exit(1)
