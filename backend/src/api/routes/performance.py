"""
绩效分析API路由
"""

from typing import List
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from src.core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


# ===== 响应模型 =====

class PerformanceMetricsResponse(BaseModel):
    """绩效指标响应"""
    total_return: float = Field(..., description="总收益")
    total_return_percentage: float = Field(..., description="总收益率(%)")
    sharpe_ratio: float = Field(..., description="夏普比率")
    max_drawdown: float = Field(..., description="最大回撤")
    max_drawdown_percentage: float = Field(..., description="最大回撤(%)")
    win_rate: float = Field(..., description="胜率(%)")
    total_trades: int = Field(..., description="总交易次数")
    profitable_trades: int = Field(..., description="盈利交易次数")
    losing_trades: int = Field(..., description="亏损交易次数")
    average_profit: float = Field(..., description="平均盈利")
    average_loss: float = Field(..., description="平均亏损")
    profit_factor: float = Field(..., description="盈亏比")


class EquityPointResponse(BaseModel):
    """净值曲线数据点"""
    timestamp: str
    value: float


# ===== Mock数据生成器 =====

def create_mock_performance_metrics() -> PerformanceMetricsResponse:
    """创建模拟绩效指标"""
    import random

    total_trades = random.randint(50, 200)
    profitable_trades = int(total_trades * random.uniform(0.55, 0.75))
    losing_trades = total_trades - profitable_trades
    win_rate = (profitable_trades / total_trades * 100) if total_trades > 0 else 0

    return PerformanceMetricsResponse(
        total_return=random.uniform(5000, 20000),
        total_return_percentage=random.uniform(10, 40),
        sharpe_ratio=random.uniform(1.5, 3.0),
        max_drawdown=random.uniform(-3000, -1000),
        max_drawdown_percentage=random.uniform(-15, -5),
        win_rate=win_rate,
        total_trades=total_trades,
        profitable_trades=profitable_trades,
        losing_trades=losing_trades,
        average_profit=random.uniform(200, 500),
        average_loss=random.uniform(-150, -80),
        profit_factor=random.uniform(1.5, 2.5),
    )


def create_mock_equity_curve(
    start_date: str | None = None,
    end_date: str | None = None,
) -> List[EquityPointResponse]:
    """创建模拟净值曲线"""
    import random

    # 解析日期或使用默认值
    if end_date:
        end = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
    else:
        end = datetime.now(timezone.utc)

    if start_date:
        start = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
    else:
        start = end - timedelta(days=30)

    # 生成数据点
    points = []
    current = start
    value = 50000.0  # 初始资金

    while current <= end:
        # 添加随机波动
        daily_return = random.uniform(-0.02, 0.03)
        value = value * (1 + daily_return)

        points.append(EquityPointResponse(
            timestamp=current.isoformat(),
            value=value,
        ))

        current += timedelta(days=1)

    return points


# ===== API端点 =====

@router.get("/performance/metrics", response_model=PerformanceMetricsResponse)
async def get_performance_metrics(
    start_date: str | None = Query(None, description="开始日期 YYYY-MM-DD (UTC)"),
    end_date: str | None = Query(None, description="结束日期 YYYY-MM-DD (UTC)"),
):
    """
    获取绩效指标

    返回指定时间范围的绩效统计指标
    如果不指定时间范围，返回全部历史数据的统计

    注意：日期参数使用 UTC 时区
    """
    logger.info(f"API: 获取绩效指标 start={start_date} end={end_date}")

    try:
        from src.api.server import get_app_state
        from src.services.performance_service import PerformanceService
        from datetime import date

        app_state = get_app_state()
        db_manager = app_state.get("db_manager")

        if not db_manager:
            logger.warning("Database not initialized, returning zero values")
            return PerformanceMetricsResponse(
                total_return=0.0,
                total_return_percentage=0.0,
                sharpe_ratio=0.0,
                max_drawdown=0.0,
                max_drawdown_percentage=0.0,
                win_rate=0.0,
                total_trades=0,
                profitable_trades=0,
                losing_trades=0,
                average_profit=0.0,
                average_loss=0.0,
                profit_factor=0.0,
            )

        # 解析日期参数
        start_date_obj = None
        end_date_obj = None
        if start_date:
            start_date_obj = date.fromisoformat(start_date)
        if end_date:
            end_date_obj = date.fromisoformat(end_date)

        # 使用PerformanceService获取绩效摘要
        from src.core.config import get_config
        config = get_config()
        exchange_name = "binanceusdm" if config.binance_futures else (config.data_source_exchange or "binance")

        performance_service = PerformanceService(
            db_manager=db_manager,
            exchange_name=exchange_name
        )

        summary = await performance_service.get_performance_summary(
            start_date=start_date_obj,
            end_date=end_date_obj,
            use_cache=True
        )

        return PerformanceMetricsResponse(
            total_return=summary["total_return"],
            total_return_percentage=summary["total_return_percentage"],
            sharpe_ratio=summary["sharpe_ratio"],
            max_drawdown=summary["max_drawdown"],
            max_drawdown_percentage=summary["max_drawdown_percentage"],
            win_rate=summary["win_rate"],
            total_trades=summary["total_trades"],
            profitable_trades=summary["profitable_trades"],
            losing_trades=summary["losing_trades"],
            average_profit=summary["average_profit"],
            average_loss=summary["average_loss"],
            profit_factor=summary["profit_factor"],
        )

    except Exception as e:
        logger.error(f"获取绩效指标失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/performance/equity-curve", response_model=List[EquityPointResponse])
async def get_equity_curve(
    start_date: str | None = Query(None, description="开始日期(ISO格式)"),
    end_date: str | None = Query(None, description="结束日期(ISO格式)"),
):
    """
    获取净值曲线

    返回指定时间范围内的净值曲线数据点
    """
    logger.info(f"API: 获取净值曲线 start={start_date} end={end_date}")

    try:
        from src.api.server import get_app_state
        from src.services.database import TradingDAO
        from src.core.config import get_config
        from datetime import date

        app_state = get_app_state()
        db_manager = app_state.get("db_manager")

        if not db_manager:
            logger.warning("Database not initialized, returning empty array")
            return []

        # 解析日期参数
        start_date_obj = None
        end_date_obj = None
        if start_date:
            start_date_obj = date.fromisoformat(start_date.split('T')[0])
        if end_date:
            end_date_obj = date.fromisoformat(end_date.split('T')[0])

        # 从数据库获取真实数据
        async with db_manager.get_session() as session:
            dao = TradingDAO(session)
            config = get_config()
            exchange_name = "binanceusdm" if config.binance_futures else (config.data_source_exchange or "binance")
            snapshots = await dao.get_portfolio_snapshots(
                start_date=start_date_obj,
                end_date=end_date_obj,
                limit=None,  # 有日期范围时不限制，返回该范围内所有数据
                exchange_name=exchange_name,
            )

            # 获取初始资金配置
            from sqlalchemy import text
            initial_capital = None
            initial_capital_time = None
            result_ic = await session.execute(
                text("SELECT initial_capital, set_at FROM account_settings WHERE exchange_id = (SELECT id FROM exchanges WHERE name = :name)"),
                {"name": exchange_name}
            )
            ic_row = result_ic.fetchone()
            if ic_row:
                initial_capital = float(ic_row[0])
                initial_capital_time = ic_row[1]

            # 如果没有数据，返回空数组
            if len(snapshots) < 1:
                logger.info(f"No snapshots found, returning empty array")
                return []

            # 如果查询单日且快照不足2个，补充前一天的最后快照
            if len(snapshots) < 2 and start_date_obj and end_date_obj and start_date_obj == end_date_obj:
                from datetime import timedelta
                previous_day = start_date_obj - timedelta(days=1)
                previous_snapshots = await dao.get_portfolio_snapshots(
                    start_date=previous_day,
                    end_date=previous_day,
                    limit=1,  # 只要最新的一个
                    exchange_name=exchange_name,
                )
                if previous_snapshots:
                    # 将前一天的快照添加到列表开头（因为后面会reverse）
                    snapshots.append(previous_snapshots[0])
                    logger.debug(f"单日净值曲线快照不足，补充前一天快照: {previous_snapshots[0].datetime}")

            # 转换为响应格式
            result = []

            # 如果有初始资金配置，添加为第一个点
            if initial_capital and initial_capital_time:
                if initial_capital_time.tzinfo is None:
                    ic_time_with_tz = initial_capital_time.replace(tzinfo=timezone.utc)
                else:
                    ic_time_with_tz = initial_capital_time
                result.append(EquityPointResponse(
                    timestamp=ic_time_with_tz.isoformat(),
                    value=initial_capital
                ))

            for snapshot in reversed(snapshots):  # 从旧到新排序
                # 确保时间戳包含时区信息
                if snapshot.datetime:
                    if snapshot.datetime.tzinfo is None:
                        # 如果没有时区信息，假设是UTC
                        dt_with_tz = snapshot.datetime.replace(tzinfo=timezone.utc)
                        timestamp_str = dt_with_tz.isoformat()
                    else:
                        timestamp_str = snapshot.datetime.isoformat()
                else:
                    # 如果只有日期，转换为UTC的当天开始时间
                    from datetime import time
                    dt_with_tz = datetime.combine(snapshot.snapshot_date, time.min, tzinfo=timezone.utc)
                    timestamp_str = dt_with_tz.isoformat()

                result.append(EquityPointResponse(
                    timestamp=timestamp_str,
                    value=float(snapshot.wallet_balance if snapshot.wallet_balance else snapshot.total_value)
                ))

            return result

    except Exception as e:
        logger.error(f"获取净值曲线失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/performance/trades-stats")
async def get_trades_stats():
    """
    获取交易统计

    返回交易统计数据（如盈亏分布、持仓时长等）
    """
    logger.info("API: 获取交易统计")

    try:
        from src.api.server import get_app_state
        from src.services.database import TradingDAO

        app_state = get_app_state()
        db_manager = app_state.get("db_manager")

        if not db_manager:
            logger.warning("Database not initialized, returning empty data")
            return {
                "profit_distribution": {},
                "holding_period": {},
            }

        # 从数据库获取历史交易数据
        async with db_manager.get_session() as session:
            dao = TradingDAO(session)
            closed_positions = await dao.get_closed_positions(limit=1000)

            if not closed_positions:
                logger.info("No closed positions found")
                return {
                    "profit_distribution": {},
                    "holding_period": {},
                }

            # 计算盈亏分布
            profit_distribution = {
                "-1000以下": 0,
                "-1000~-500": 0,
                "-500~-100": 0,
                "-100~0": 0,
                "0~100": 0,
                "100~500": 0,
                "500~1000": 0,
                "1000以上": 0,
            }

            for cp in closed_positions:
                pnl = float(cp.realized_pnl)
                if pnl < -1000:
                    profit_distribution["-1000以下"] += 1
                elif pnl < -500:
                    profit_distribution["-1000~-500"] += 1
                elif pnl < -100:
                    profit_distribution["-500~-100"] += 1
                elif pnl < 0:
                    profit_distribution["-100~0"] += 1
                elif pnl < 100:
                    profit_distribution["0~100"] += 1
                elif pnl < 500:
                    profit_distribution["100~500"] += 1
                elif pnl < 1000:
                    profit_distribution["500~1000"] += 1
                else:
                    profit_distribution["1000以上"] += 1

            # 计算持仓时长分布
            holding_period = {
                "< 1小时": 0,
                "1~4小时": 0,
                "4~24小时": 0,
                "1~7天": 0,
                "> 7天": 0,
            }

            for cp in closed_positions:
                if cp.holding_duration_seconds is None:
                    continue

                hours = cp.holding_duration_seconds / 3600
                days = hours / 24

                if hours < 1:
                    holding_period["< 1小时"] += 1
                elif hours < 4:
                    holding_period["1~4小时"] += 1
                elif hours < 24:
                    holding_period["4~24小时"] += 1
                elif days < 7:
                    holding_period["1~7天"] += 1
                else:
                    holding_period["> 7天"] += 1

            return {
                "profit_distribution": profit_distribution,
                "holding_period": holding_period,
            }

    except Exception as e:
        logger.error(f"获取交易统计失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
