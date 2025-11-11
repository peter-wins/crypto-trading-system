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
async def get_performance_metrics():
    """
    获取绩效指标

    返回当前的绩效统计指标
    """
    logger.info("API: 获取绩效指标")

    try:
        from src.api.server import get_app_state
        from src.database.dao import TradingDAO

        app_state = get_app_state()
        db_manager = app_state.get("db_manager")

        if not db_manager:
            logger.warning("Database not initialized, returning mock data")
            return create_mock_performance_metrics()

        # 从数据库获取真实数据并计算指标
        async with db_manager.get_session() as session:
            dao = TradingDAO(session)

            # 获取持仓数据和历史交易数据
            positions = await dao.get_open_positions()
            snapshots = await dao.get_portfolio_snapshots(limit=30)
            closed_positions = await dao.get_closed_positions(limit=1000)  # 获取所有历史交易

            # 如果没有足够数据，返回模拟数据
            if len(snapshots) < 2:
                logger.info("Not enough data for performance calculation, returning mock data")
                return create_mock_performance_metrics()

            # 计算基本统计（基于当前持仓的未实现盈亏）
            unrealized_pnl = sum(float(p.unrealized_pnl) for p in positions)

            # 计算已实现盈亏（从历史交易）
            realized_pnl = sum(float(cp.realized_pnl) for cp in closed_positions)

            # 总收益 = 已实现盈亏 + 未实现盈亏
            total_return = realized_pnl + unrealized_pnl

            # 计算总投入（从快照获取初始资金）
            initial_value = float(snapshots[-1].total_value) if snapshots else 50000.0
            total_return_percentage = (total_return / initial_value * 100) if initial_value > 0 else 0

            # 计算最大回撤
            values = [float(s.total_value) for s in reversed(snapshots)]
            max_drawdown = 0
            peak = values[0]
            for value in values:
                if value > peak:
                    peak = value
                drawdown = value - peak
                if drawdown < max_drawdown:
                    max_drawdown = drawdown
            max_drawdown_percentage = (max_drawdown / peak * 100) if peak > 0 else 0

            # 简化的夏普比率计算（使用日收益率）
            returns = []
            for i in range(1, len(values)):
                daily_return = (values[i] - values[i-1]) / values[i-1]
                returns.append(daily_return)

            import statistics
            avg_return = statistics.mean(returns) if returns else 0
            std_return = statistics.stdev(returns) if len(returns) > 1 else 0.01
            sharpe_ratio = (avg_return / std_return * (252 ** 0.5)) if std_return > 0 else 0  # 年化

            # 从历史交易计算交易统计
            total_trades = len(closed_positions)
            profitable_trades = sum(1 for cp in closed_positions if float(cp.realized_pnl) > 0)
            losing_trades = sum(1 for cp in closed_positions if float(cp.realized_pnl) < 0)
            win_rate = (profitable_trades / total_trades * 100) if total_trades > 0 else 0.0

            # 计算平均盈利和亏损
            profits = [float(cp.realized_pnl) for cp in closed_positions if float(cp.realized_pnl) > 0]
            losses = [float(cp.realized_pnl) for cp in closed_positions if float(cp.realized_pnl) < 0]
            average_profit = statistics.mean(profits) if profits else 0.0
            average_loss = statistics.mean(losses) if losses else 0.0

            # 计算盈亏比
            total_profit = sum(profits) if profits else 0.0
            total_loss = abs(sum(losses)) if losses else 0.0
            profit_factor = (total_profit / total_loss) if total_loss > 0 else 0.0

            return PerformanceMetricsResponse(
                total_return=total_return,
                total_return_percentage=total_return_percentage,
                sharpe_ratio=sharpe_ratio,
                max_drawdown=max_drawdown,
                max_drawdown_percentage=max_drawdown_percentage,
                win_rate=win_rate,
                total_trades=total_trades,
                profitable_trades=profitable_trades,
                losing_trades=losing_trades,
                average_profit=average_profit,
                average_loss=average_loss,
                profit_factor=profit_factor,
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
        from src.database.dao import TradingDAO
        from datetime import date

        app_state = get_app_state()
        db_manager = app_state.get("db_manager")

        if not db_manager:
            logger.warning("Database not initialized, returning mock data")
            return create_mock_equity_curve(start_date, end_date)

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
            snapshots = await dao.get_portfolio_snapshots(
                start_date=start_date_obj,
                end_date=end_date_obj,
                limit=365  # 最多返回一年的数据
            )

            # 如果没有数据，生成模拟数据用于展示
            if len(snapshots) < 1:
                logger.info(f"No snapshots found, generating mock data for visualization")
                return create_mock_equity_curve(start_date, end_date)

            # 转换为响应格式
            result = []
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
        from src.database.dao import TradingDAO

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
