"""
测试绩效服务

演示如何使用PerformanceService
"""

import asyncio
from datetime import date, timedelta

from src.core.config import get_config
from src.services.database import get_db_manager
from src.services.performance_service import PerformanceService


async def main():
    """测试主函数"""
    config = get_config()

    # 初始化数据库
    db_manager = get_db_manager(config.database_url)

    # 创建绩效服务
    performance_service = PerformanceService(
        db_manager=db_manager,
        exchange_name="binanceusdm"
    )

    print("=" * 60)
    print("绩效服务测试")
    print("=" * 60)

    # 测试1: 计算并保存昨天的绩效
    print("\n1. 计算并保存昨天的绩效")
    yesterday = date.today() - timedelta(days=1)
    result = await performance_service.calculate_and_save_daily_performance(
        target_date=yesterday,
        force=True  # 强制重新计算
    )
    if result:
        print(f"   ✓ 已保存 {yesterday} 的绩效指标")
        print(f"   - 总收益: ${float(result.total_return):.2f}")
        print(f"   - 胜率: {float(result.win_rate):.2f}%")
        print(f"   - 总交易: {result.total_trades}")
    else:
        print(f"   ✗ {yesterday} 数据不足，无法计算")

    # 测试2: 获取绩效摘要
    print("\n2. 获取最近7天绩效摘要")
    start_date = date.today() - timedelta(days=7)
    summary = await performance_service.get_performance_summary(
        start_date=start_date,
        end_date=date.today()
    )
    print(f"   总收益: ${summary['total_return']:.2f}")
    print(f"   总收益率: {summary['total_return_percentage']:.2f}%")
    print(f"   胜率: {summary['win_rate']:.2f}%")
    print(f"   夏普比率: {summary['sharpe_ratio']:.2f}")

    # 测试3: 格式化供AI使用
    print("\n3. 格式化绩效数据供AI使用")
    ai_text = await performance_service.format_for_ai(period="weekly")
    print(ai_text)

    # 测试4: 获取绩效趋势
    print("\n4. 获取最近7天绩效趋势")
    trend = await performance_service.get_recent_performance_trend(days=7)
    if trend:
        print("   日期        | 收益     | 胜率    | 交易数")
        print("   " + "-" * 45)
        for day in trend:
            print(f"   {day['date']} | ${day['return']:7.2f} | {day['win_rate']:5.1f}% | {day['trades']:3d}")
    else:
        print("   暂无历史数据")

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
