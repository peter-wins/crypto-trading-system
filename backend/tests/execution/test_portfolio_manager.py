from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.execution.portfolio import PortfolioManager
from src.models.portfolio import Portfolio
from src.models.trade import OrderSide, Position


pytestmark = pytest.mark.asyncio


def _create_initial_portfolio() -> Portfolio:
    now = datetime.now(timezone.utc)
    position = Position(
        symbol="BTC/USDT",
        side=OrderSide.BUY,
        amount=Decimal("0.3"),
        entry_price=Decimal("20000"),
        current_price=Decimal("21000"),
        unrealized_pnl=Decimal("300"),
        unrealized_pnl_percentage=Decimal("1.5"),
        value=Decimal("6300"),
        stop_loss=None,
        take_profit=None,
    )
    return Portfolio(
        timestamp=int(now.timestamp() * 1000),
        dt=now,
        total_value=Decimal("12000"),
        cash=Decimal("5700"),
        positions=[position],
        total_pnl=Decimal("0"),
        daily_pnl=Decimal("0"),
        total_return=Decimal("0"),
    )


async def test_get_current_portfolio_paper():
    manager = PortfolioManager(paper_trading=True, initial_portfolio=_create_initial_portfolio())
    portfolio = await manager.get_current_portfolio()

    assert portfolio.cash == Decimal("5700")
    assert len(portfolio.positions) == 1


async def test_apply_fill_updates_portfolio():
    manager = PortfolioManager(paper_trading=True, initial_portfolio=_create_initial_portfolio())
    await manager.get_current_portfolio()
    manager.apply_fill("BTC/USDT", OrderSide.BUY, Decimal("0.1"), Decimal("20500"))

    portfolio = await manager.get_current_portfolio()
    position = portfolio.get_position("BTC/USDT")
    assert position is not None
    assert position.amount > Decimal("0.3")


async def test_calculate_metrics_returns_performance():
    manager = PortfolioManager(paper_trading=True, initial_portfolio=_create_initial_portfolio())
    metrics = await manager.calculate_metrics()

    assert metrics.total_return == Decimal("0")
    assert metrics.total_trades == 0
