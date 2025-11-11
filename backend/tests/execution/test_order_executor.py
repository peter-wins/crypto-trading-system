from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from src.execution.order import CCXTOrderExecutor
from src.models.trade import OrderSide, OrderType


pytestmark = pytest.mark.asyncio


async def test_create_order_paper_trading():
    executor = CCXTOrderExecutor(paper_trading=True)
    order = await executor.create_order(
        symbol="BTC/USDT",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        amount=Decimal("0.1"),
        price=Decimal("20000"),
    )

    assert order.symbol == "BTC/USDT"
    assert order.amount == Decimal("0.1")
    assert order.status.value in {"filled", "open"}


async def test_cancel_order_paper_trading():
    executor = CCXTOrderExecutor(paper_trading=True)
    order = await executor.create_order(
        symbol="ETH/USDT",
        side=OrderSide.SELL,
        order_type=OrderType.LIMIT,
        amount=Decimal("1"),
        price=Decimal("1500"),
    )

    result = await executor.cancel_order(order.id, "ETH/USDT")
    assert result is True
    stored = await executor.get_order(order.id, "ETH/USDT")
    assert stored.status.value == "canceled"


async def test_get_open_orders_paper_trading():
    executor = CCXTOrderExecutor(paper_trading=True)
    await executor.create_order(
        symbol="BTC/USDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        amount=Decimal("0.2"),
        price=Decimal("19000"),
    )

    open_orders = await executor.get_open_orders("BTC/USDT")
    assert len(open_orders) == 1
    assert open_orders[0].symbol == "BTC/USDT"


async def test_get_order_not_found_paper_trading():
    executor = CCXTOrderExecutor(paper_trading=True)
    with pytest.raises(Exception):
        await executor.get_order("unknown", "BTC/USDT")
