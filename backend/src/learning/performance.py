"""
学习模块 · 绩效评估器

提供交易级/周期级的绩效统计以及与基准对比功能。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, getcontext
from typing import Any, Dict, Iterable, List, Optional, Sequence

import math

from src.core.logger import get_logger
from src.models.decision import DecisionRecord
from src.models.performance import PerformanceMetrics
from src.models.trade import Trade


logger = get_logger(__name__)

# 提高小数精度，避免浮点累计误差
getcontext().prec = 28


def _safe_decimal(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return default


def _calculate_daily_returns(equity_curve: Sequence[Decimal]) -> List[Decimal]:
    returns: List[Decimal] = []
    for prev, curr in zip(equity_curve, equity_curve[1:]):
        if prev == 0:
            returns.append(Decimal("0"))
        else:
            returns.append((curr - prev) / prev)
    return returns


def _calculate_sharpe_ratio(daily_returns: Sequence[Decimal], risk_free: Decimal = Decimal("0")) -> Decimal:
    if not daily_returns:
        return Decimal("0")
    excess = [r - risk_free for r in daily_returns]
    mean = sum(excess) / Decimal(len(excess))
    variance = sum((r - mean) ** 2 for r in excess) / Decimal(len(excess) or 1)
    std = Decimal(math.sqrt(float(variance)))
    if std == 0:
        return Decimal("0")
    # 年化假设 252 个交易日
    return mean / std * Decimal(math.sqrt(252))


def _calculate_sortino_ratio(daily_returns: Sequence[Decimal], risk_free: Decimal = Decimal("0")) -> Decimal:
    if not daily_returns:
        return Decimal("0")
    downside = [min(r - risk_free, Decimal("0")) for r in daily_returns]
    mean = sum(r - risk_free for r in daily_returns) / Decimal(len(daily_returns))
    downside_sq = sum(d ** 2 for d in downside) / Decimal(len(daily_returns) or 1)
    downside_std = Decimal(math.sqrt(float(downside_sq)))
    if downside_std == 0:
        return Decimal("0")
    return mean / downside_std * Decimal(math.sqrt(252))


def _calculate_max_drawdown(equity_curve: Sequence[Decimal]) -> Decimal:
    max_value = Decimal("-Infinity")
    max_drawdown = Decimal("0")
    for value in equity_curve:
        max_value = max(max_value, value)
        drawdown = (value - max_value) / max_value if max_value > 0 else Decimal("0")
        max_drawdown = min(max_drawdown, drawdown)
    return abs(max_drawdown)


def _calculate_calmar_ratio(total_return: Decimal, max_drawdown: Decimal) -> Decimal:
    if max_drawdown == 0:
        return Decimal("0")
    return total_return / max_drawdown


def _calculate_profit_factor(trades: Sequence[Trade]) -> Decimal:
    gains = Decimal("0")
    losses = Decimal("0")
    for trade in trades:
        pnl = _safe_decimal(trade.cost)
        if pnl > 0:
            gains += pnl
        elif pnl < 0:
            losses += abs(pnl)
    if losses == 0:
        return Decimal("0")
    return gains / losses


def _holding_period(entry: DecisionRecord, exit: DecisionRecord) -> timedelta:
    return exit.dt - entry.dt


class PerformanceEvaluator:
    """
    绩效评估器实现。

    当前主要依赖传入的数据进行计算，未来可接入 PortfolioManager / 数据库获取完整历史。
    """

    def __init__(self) -> None:
        self.logger = logger

    async def evaluate_trade(
        self,
        trade: Trade,
        entry_decision: DecisionRecord,
        exit_decision: DecisionRecord,
    ) -> Dict[str, Any]:
        """
        评估单笔成交，输出盈亏和持仓时间等指标。
        """
        pnl = _safe_decimal(trade.cost)
        entry_price = _safe_decimal(entry_decision.input_context.get("price"))
        exit_price = _safe_decimal(exit_decision.input_context.get("price"))

        pnl_percentage = Decimal("0")
        if entry_price > 0:
            pnl_percentage = (exit_price - entry_price) / entry_price * Decimal("100")

        holding_period = _holding_period(entry_decision, exit_decision)
        outcome = "success" if pnl > 0 else "failure" if pnl < 0 else "break_even"

        analysis = (
            f"持仓 {holding_period}，入场价 {entry_price}, 离场价 {exit_price}, "
            f"盈亏 {pnl} ({pnl_percentage:.2f}%)。"
        )

        return {
            "trade_id": trade.id,
            "symbol": trade.symbol,
            "pnl": pnl,
            "pnl_percentage": pnl_percentage,
            "holding_period": holding_period,
            "outcome": outcome,
            "analysis": analysis,
        }

    async def evaluate_period(
        self,
        start_date: datetime,
        end_date: datetime,
        *,
        equity_curve: Optional[Sequence[Decimal]] = None,
        trades: Optional[Sequence[Trade]] = None,
    ) -> PerformanceMetrics:
        """
        综合评估指定周期的收益表现。

        Args:
            equity_curve: 每日/每周期的权益值序列（含起点和终点）
            trades: 周期内成交列表
        """
        if not equity_curve or len(equity_curve) < 2:
            raise ValueError("equity_curve 至少需要两个数据点")

        total_return = (
            (equity_curve[-1] - equity_curve[0]) / equity_curve[0] * Decimal("100")
            if equity_curve[0] > 0
            else Decimal("0")
        )

        days = max((end_date - start_date).days, 1)
        annualized_return = total_return / Decimal(days) * Decimal("365")

        daily_returns = _calculate_daily_returns(equity_curve)
        volatility = Decimal(math.sqrt(float(sum((r) ** 2 for r in daily_returns) / (len(daily_returns) or 1)))) * Decimal(
            math.sqrt(252)
        )
        max_drawdown = _calculate_max_drawdown(equity_curve)
        sharpe_ratio = _calculate_sharpe_ratio(daily_returns)
        sortino_ratio = _calculate_sortino_ratio(daily_returns)
        calmar_ratio = _calculate_calmar_ratio(total_return, max_drawdown) if max_drawdown else Decimal("0")

        trades = trades or []
        total_trades = len(trades)
        winning_trades = sum(1 for t in trades if _safe_decimal(t.cost) > 0)
        losing_trades = sum(1 for t in trades if _safe_decimal(t.cost) < 0)
        win_rate = Decimal(winning_trades) / Decimal(total_trades) if total_trades > 0 else Decimal("0")

        avg_win = (
            sum(_safe_decimal(t.cost) for t in trades if _safe_decimal(t.cost) > 0) / Decimal(winning_trades)
            if winning_trades
            else Decimal("0")
        )
        avg_loss = (
            sum(abs(_safe_decimal(t.cost)) for t in trades if _safe_decimal(t.cost) < 0) / Decimal(losing_trades)
            if losing_trades
            else Decimal("0")
        )

        profit_factor = _calculate_profit_factor(trades)

        # 最大连胜/连败统计
        max_wins = max_losses = curr_wins = curr_losses = 0
        for trade in trades:
            pnl = _safe_decimal(trade.cost)
            if pnl > 0:
                curr_wins += 1
                curr_losses = 0
            elif pnl < 0:
                curr_losses += 1
                curr_wins = 0
            max_wins = max(max_wins, curr_wins)
            max_losses = max(max_losses, curr_losses)

        metrics = PerformanceMetrics(
            start_date=start_date,
            end_date=end_date,
            total_return=total_return,
            annualized_return=annualized_return,
            daily_returns=daily_returns,
            volatility=volatility,
            max_drawdown=max_drawdown * Decimal("100"),
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            calmar_ratio=calmar_ratio,
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate * Decimal("100"),
            avg_win=avg_win,
            avg_loss=avg_loss,
            profit_factor=profit_factor,
            max_consecutive_wins=max_wins,
            max_consecutive_losses=max_losses,
        )
        return metrics

    async def compare_with_benchmark(
        self,
        period_metrics: PerformanceMetrics,
        benchmark_metrics: PerformanceMetrics,
    ) -> Dict[str, Any]:
        """
        与基准（如 BTC/USDT）比较。

        Args:
            period_metrics: 策略自身指标
            benchmark_metrics: 基准指标
        """
        alpha = period_metrics.total_return - benchmark_metrics.total_return
        beta = (
            period_metrics.volatility / benchmark_metrics.volatility
            if benchmark_metrics.volatility != 0
            else Decimal("0")
        )
        excess_return = period_metrics.annualized_return - benchmark_metrics.annualized_return

        return {
            "alpha": alpha,
            "beta": beta,
            "excess_return": excess_return,
            "strategy_sharpe": period_metrics.sharpe_ratio,
            "benchmark_sharpe": benchmark_metrics.sharpe_ratio,
        }
