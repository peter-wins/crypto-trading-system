"""
批量补充历史绩效数据

回溯计算所有历史日期的绩效指标并存储到数据库
"""

import asyncio
from datetime import date, timedelta

from src.core.config import get_config
from src.services.database import get_db_manager, TradingDAO
from src.services.performance_service import PerformanceService


async def main():
    """批量计算历史绩效"""
    config = get_config()
    db_manager = get_db_manager(config.database_url)

    exchange_name = "binanceusdm" if config.binance_futures else (config.data_source_exchange or "binance")

    print("=" * 60)
    print("批量补充历史绩效数据")
    print("=" * 60)

    # 1. 获取数据库中最早和最晚的快照日期
    async with db_manager.get_session() as session:
        dao = TradingDAO(session)
        snapshots = await dao.get_portfolio_snapshots(
            limit=10000,
            exchange_name=exchange_name
        )

        if not snapshots:
            print("数据库中没有快照数据，无法计算历史绩效")
            return

        # 获取日期范围
        dates = [s.snapshot_date for s in snapshots if s.snapshot_date]
        if not dates:
            print("快照数据没有日期信息")
            return

        earliest_date = min(dates)
        latest_date = max(dates)

        print(f"\n数据库快照日期范围:")
        print(f"  最早: {earliest_date}")
        print(f"  最晚: {latest_date}")
        print(f"  总快照数: {len(snapshots)}")

    # 2. 创建绩效服务
    performance_service = PerformanceService(
        db_manager=db_manager,
        exchange_name=exchange_name
    )

    # 3. 逐日计算绩效
    print(f"\n开始计算历史绩效...")

    current_date = earliest_date
    success_count = 0
    skip_count = 0
    error_count = 0

    while current_date < date.today():
        try:
            # 检查是否已存在
            async with db_manager.get_session() as session:
                dao = TradingDAO(session)
                existing = await dao.get_performance_metrics(
                    start_date=current_date,
                    end_date=current_date,
                    exchange_name=exchange_name
                )

                if existing:
                    print(f"  {current_date}: 已存在，跳过")
                    skip_count += 1
                    current_date += timedelta(days=1)
                    continue

            # 计算并保存
            result = await performance_service.calculate_and_save_daily_performance(
                target_date=current_date,
                force=False
            )

            if result:
                print(f"  ✓ {current_date}: 收益${float(result.total_return):.2f}, 胜率{float(result.win_rate):.1f}%, 交易{result.total_trades}笔")
                success_count += 1
            else:
                print(f"  - {current_date}: 数据不足，跳过")
                skip_count += 1

        except Exception as e:
            print(f"  ✗ {current_date}: 计算失败 - {e}")
            error_count += 1

        current_date += timedelta(days=1)

    # 4. 统计结果
    print("\n" + "=" * 60)
    print("批量计算完成")
    print("=" * 60)
    print(f"成功计算: {success_count} 天")
    print(f"跳过: {skip_count} 天")
    print(f"失败: {error_count} 天")
    print("=" * 60)

    # 5. 显示完整趋势
    if success_count > 0:
        print("\n历史绩效趋势:")
        trend = await performance_service.get_recent_performance_trend(days=30)
        if trend:
            print("   日期        | 收益     | 胜率    | 交易数")
            print("   " + "-" * 45)
            for day in trend:
                print(f"   {day['date']} | ${day['return']:7.2f} | {day['win_rate']:5.1f}% | {day['trades']:3d}")


if __name__ == "__main__":
    asyncio.run(main())
