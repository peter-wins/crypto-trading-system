from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from src.learning.performance import PerformanceEvaluator
from src.models.decision import DecisionRecord
from src.models.performance import PerformanceMetrics
from src.models.trade import OrderSide, OrderStatus, OrderType, Trade


pytestmark = pytest.mark.asyncio


def _make_trade(profit: Decimal) -> Trade:
    now = datetime.now(timezone.utc)
    return Trade(
        id="trade-1",
        order_id="order-1",
        timestamp=int(now.timestamp() * 1000),
        dt=now,
        symbol="BTC/USDT",
        side=OrderSide.BUY,
        price=Decimal("100"),
        amount=Decimal("1"),
        cost=profit,
        fee=None,
        fee_currency=None,
    )


def _make_decision(decision_id: str, price: Decimal) -> DecisionRecord:
    now = datetime.now(timezone.utc)
    return DecisionRecord(
        id=decision_id,
        timestamp=int(now.timestamp() * 1000),
        dt=now,
        input_context={"price": str(price)},
        thought_process="",
        tools_used=[],
        decision="",
        action_taken=None,
        decision_layer="tactical",
        model_used="rule_based",
    )


async def test_evaluate_trade_profit():
    evaluator = PerformanceEvaluator()
    trade = _make_trade(Decimal("50"))
    entry = _make_decision("entry", Decimal("100"))
    exit_decision = _make_decision("exit", Decimal("150"))
    result = await evaluator.evaluate_trade(trade, entry, exit_decision)

    assert result["pnl"] == Decimal("50")
    assert result["outcome"] == "success"
    assert isinstance(result["holding_period"], timedelta)


async def test_evaluate_period_basic_metrics():
    evaluator = PerformanceEvaluator()
    start = datetime(2025, 1, 1)
    end = datetime(2025, 1, 4)
    equity_curve = [
        Decimal("1000"),
        Decimal("1050"),
        Decimal("1020"),
        Decimal("1100"),
    ]
    trades = [
        _make_trade(Decimal("50")),
        _make_trade(Decimal("-30")),
        _make_trade(Decimal("80")),
    ]

    metrics = await evaluator.evaluate_period(
        start,
        end,
        equity_curve=equity_curve,
        trades=trades,
    )

    assert isinstance(metrics, PerformanceMetrics)
    assert metrics.total_trades == 3
    assert metrics.winning_trades == 2
    assert metrics.losing_trades == 1
    assert metrics.daily_returns
    assert metrics.max_consecutive_wins >= 1


async def test_compare_with_benchmark():
    evaluator = PerformanceEvaluator()
    now = datetime.now(timezone.utc)
    strat = PerformanceMetrics(
        start_date=now,
        end_date=now,
        total_return=Decimal("15"),
        annualized_return=Decimal("45"),
        daily_returns=[Decimal("0.05")],
        volatility=Decimal("0.2"),
        max_drawdown=Decimal("5"),
        sharpe_ratio=Decimal("1.2"),
        sortino_ratio=Decimal("1"),
        calmar_ratio=Decimal("0.8"),
        total_trades=10,
        winning_trades=7,
        losing_trades=3,
        win_rate=Decimal("0.7"),
        avg_win=Decimal("30"),
        avg_loss=Decimal("20"),
        profit_factor=Decimal("1.5"),
        max_consecutive_wins=4,
        max_consecutive_losses=2,
    )
    bench = PerformanceMetrics(
        start_date=now,
        end_date=now,
        total_return=Decimal("10"),
        annualized_return=Decimal("30"),
        daily_returns=[Decimal("0.03")],
        volatility=Decimal("0.15"),
        max_drawdown=Decimal("4"),
        sharpe_ratio=Decimal("1.0"),
        sortino_ratio=Decimal("0.8"),
        calmar_ratio=Decimal("0.75"),
        total_trades=0,
        winning_trades=0,
        losing_trades=0,
        win_rate=Decimal("0"),
        avg_win=Decimal("0"),
        avg_loss=Decimal("0"),
        profit_factor=Decimal("0"),
        max_consecutive_wins=0,
        max_consecutive_losses=0,
    )

    result = await evaluator.compare_with_benchmark(strat, bench)
    assert result["alpha"] == Decimal("5")
    assert result["beta"] != 0
