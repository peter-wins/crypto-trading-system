"""Tests for trade models"""

import pytest
from datetime import datetime, timezone
from decimal import Decimal

from src.models.trade import (
    Order, OrderSide, OrderType, OrderStatus,
    Trade, Position
)


def test_order_creation():
    """Test order model creation"""
    order = Order(
        id="order_123",
        client_order_id="client_order_456",
        timestamp=1704067200000,
        dt=datetime.now(timezone.utc),
        symbol="BTC/USDT",
        side=OrderSide.BUY,
        type=OrderType.LIMIT,
        status=OrderStatus.OPEN,
        price=Decimal("45000"),
        amount=Decimal("0.1"),
        filled=Decimal("0"),
        remaining=Decimal("0.1"),
        cost=Decimal("0"),
        exchange="binance"
    )

    assert order.id == "order_123"
    assert order.symbol == "BTC/USDT"
    assert order.side == OrderSide.BUY
    assert order.type == OrderType.LIMIT
    assert order.status == OrderStatus.OPEN
    assert order.price == Decimal("45000")
    assert order.amount == Decimal("0.1")


def test_order_enums():
    """Test order enum values"""
    assert OrderSide.BUY.value == "buy"
    assert OrderSide.SELL.value == "sell"

    assert OrderType.MARKET.value == "market"
    assert OrderType.LIMIT.value == "limit"

    assert OrderStatus.OPEN.value == "open"
    assert OrderStatus.FILLED.value == "filled"


def test_trade_creation():
    """Test trade model creation"""
    trade = Trade(
        id="trade_123",
        order_id="order_123",
        timestamp=1704067200000,
        dt=datetime.now(timezone.utc),
        symbol="BTC/USDT",
        side=OrderSide.BUY,
        price=Decimal("45000"),
        amount=Decimal("0.1"),
        cost=Decimal("4500"),
        fee=Decimal("4.5"),
        fee_currency="USDT"
    )

    assert trade.id == "trade_123"
    assert trade.order_id == "order_123"
    assert trade.price == Decimal("45000")
    assert trade.amount == Decimal("0.1")
    assert trade.cost == Decimal("4500")


def test_position_buy():
    """Test position for buy side"""
    position = Position(
        symbol="BTC/USDT",
        side=OrderSide.BUY,
        amount=Decimal("0.1"),
        entry_price=Decimal("45000"),
        current_price=Decimal("46000"),
        unrealized_pnl=Decimal("100"),
        unrealized_pnl_percentage=Decimal("2.22"),
        value=Decimal("4600")
    )

    assert position.symbol == "BTC/USDT"
    assert position.side == OrderSide.BUY
    assert position.amount == Decimal("0.1")


def test_position_update_price_buy():
    """Test position price update for buy side"""
    position = Position(
        symbol="BTC/USDT",
        side=OrderSide.BUY,
        amount=Decimal("0.1"),
        entry_price=Decimal("45000"),
        current_price=Decimal("45000"),
        unrealized_pnl=Decimal("0"),
        unrealized_pnl_percentage=Decimal("0"),
        value=Decimal("4500")
    )

    # Update to higher price (profit)
    position.update_current_price(Decimal("46000"))

    assert position.current_price == Decimal("46000")
    assert position.value == Decimal("4600")  # 0.1 * 46000
    assert position.unrealized_pnl == Decimal("100")  # (46000 - 45000) * 0.1
    # (100 / 4500) * 100 = 2.222...
    assert position.unrealized_pnl_percentage.quantize(Decimal("0.01")) == Decimal("2.22")


def test_position_update_price_sell():
    """Test position price update for sell side"""
    position = Position(
        symbol="BTC/USDT",
        side=OrderSide.SELL,
        amount=Decimal("0.1"),
        entry_price=Decimal("45000"),
        current_price=Decimal("45000"),
        unrealized_pnl=Decimal("0"),
        unrealized_pnl_percentage=Decimal("0"),
        value=Decimal("4500")
    )

    # For sell/short position, profit when price goes down
    position.update_current_price(Decimal("44000"))

    assert position.current_price == Decimal("44000")
    assert position.value == Decimal("4400")  # 0.1 * 44000
    assert position.unrealized_pnl == Decimal("100")  # (45000 - 44000) * 0.1
    # (100 / 4500) * 100 = 2.222...
    assert position.unrealized_pnl_percentage.quantize(Decimal("0.01")) == Decimal("2.22")


def test_position_with_stop_loss_take_profit():
    """Test position with stop loss and take profit"""
    position = Position(
        symbol="BTC/USDT",
        side=OrderSide.BUY,
        amount=Decimal("0.1"),
        entry_price=Decimal("45000"),
        current_price=Decimal("45000"),
        unrealized_pnl=Decimal("0"),
        unrealized_pnl_percentage=Decimal("0"),
        value=Decimal("4500"),
        stop_loss=Decimal("43000"),
        take_profit=Decimal("48000")
    )

    assert position.stop_loss == Decimal("43000")
    assert position.take_profit == Decimal("48000")
