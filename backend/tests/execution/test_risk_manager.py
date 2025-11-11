from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.execution.risk import RiskCheckResult, StandardRiskManager
from src.models.decision import TradingSignal, SignalType
from src.models.portfolio import Portfolio
from src.models.trade import OrderSide, Position


pytestmark = pytest.mark.asyncio


def _make_portfolio() -> Portfolio:
    now = datetime.now(timezone.utc)
    position = Position(
        symbol="BTC/USDT",
        side=OrderSide.BUY,
        amount=Decimal("0.5"),
        entry_price=Decimal("20000"),
        current_price=Decimal("21000"),
        unrealized_pnl=Decimal("500"),
        unrealized_pnl_percentage=Decimal("2.5"),
        value=Decimal("10500"),
        stop_loss=Decimal("19000"),
        take_profit=Decimal("23000"),
    )
    return Portfolio(
        timestamp=int(now.timestamp() * 1000),
        dt=now,
        total_value=Decimal("20000"),
        cash=Decimal("9500"),
        positions=[position],
        total_pnl=Decimal("1000"),
        daily_pnl=Decimal("-200"),
        total_return=Decimal("5"),
    )


def _make_signal() -> TradingSignal:
    now = datetime.now(timezone.utc)
    return TradingSignal(
        timestamp=int(now.timestamp() * 1000),
        dt=now,
        symbol="BTC/USDT",
        signal_type=SignalType.ENTER_LONG,
        confidence=0.7,
        suggested_price=Decimal("20500"),
        suggested_amount=Decimal("0.2"),
        reasoning="Breakout",
        supporting_factors=["Volume surge"],
        risk_factors=["High volatility"],
        source="trader",
    )


async def test_check_order_risk_passes():
    manager = StandardRiskManager()
    result = await manager.check_order_risk(
        _make_signal(),
        _make_portfolio(),
        {"max_position_size": Decimal("0.3"), "max_daily_loss": Decimal("0.1")},
    )

    assert isinstance(result, RiskCheckResult)
    assert result.passed is True


async def test_check_order_risk_fails_on_allocation():
    manager = StandardRiskManager()
    signal = _make_signal()
    # 设置大量的下单数量使仓位超限
    signal.suggested_amount = Decimal("5")
    result = await manager.check_order_risk(
        signal,
        _make_portfolio(),
        {"max_position_size": Decimal("0.1")},
    )

    assert result.passed is False
    assert "仓位占比" in (result.reason or "")


async def test_check_position_risk_triggers_stop_loss():
    manager = StandardRiskManager()
    portfolio = _make_portfolio()
    position = portfolio.positions[0]
    result = await manager.check_position_risk(position, Decimal("18500"))

    assert result.passed is False
    assert result.suggested_adjustment == {"action": "close_position"}


async def test_calculate_stop_loss_take_profit():
    manager = StandardRiskManager()
    prices = await manager.calculate_stop_loss_take_profit(
        entry_price=Decimal("20000"),
        side=OrderSide.BUY,
        risk_params={
            "stop_loss_percentage": Decimal("2"),
            "take_profit_percentage": Decimal("4"),
        },
    )

    assert prices["stop_loss"] == Decimal("19600.0000")
    assert prices["take_profit"] == Decimal("20800.0000")
