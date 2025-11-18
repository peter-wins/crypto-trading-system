"""Tests for portfolio models"""

import pytest
from datetime import datetime, timezone
from decimal import Decimal

from src.models.portfolio import Balance, AccountBalance, Portfolio
from src.models.trade import Position, OrderSide


def test_balance_creation():
    """Test balance model creation"""
    balance = Balance(
        currency="USDT",
        free=Decimal("10000"),
        used=Decimal("5000"),
        total=Decimal("15000")
    )

    assert balance.currency == "USDT"
    assert balance.free == Decimal("10000")
    assert balance.used == Decimal("5000")
    assert balance.total == Decimal("15000")


def test_account_balance_creation():
    """Test account balance model creation"""
    account_balance = AccountBalance(
        exchange="binance",
        timestamp=1704067200000,
        dt=datetime.now(timezone.utc),
        balances={
            "USDT": Balance(
                currency="USDT",
                free=Decimal("10000"),
                used=Decimal("0"),
                total=Decimal("10000")
            ),
            "BTC": Balance(
                currency="BTC",
                free=Decimal("0.1"),
                used=Decimal("0"),
                total=Decimal("0.1")
            )
        },
        total_value_usd=Decimal("14500")
    )

    assert account_balance.exchange == "binance"
    assert "USDT" in account_balance.balances
    assert "BTC" in account_balance.balances
    assert account_balance.total_value_usd == Decimal("14500")


def test_portfolio_creation():
    """Test portfolio model creation"""
    portfolio = Portfolio(
        timestamp=1704067200000,
        dt=datetime.now(timezone.utc),
        total_value=Decimal("15000"),
        cash=Decimal("10000"),
        positions=[]
    )

    assert portfolio.total_value == Decimal("15000")
    assert portfolio.cash == Decimal("10000")
    assert len(portfolio.positions) == 0
    assert portfolio.total_pnl == Decimal("0")


def test_portfolio_get_position():
    """Test getting position from portfolio"""
    position1 = Position(
        symbol="BTC/USDT",
        side=OrderSide.BUY,
        amount=Decimal("0.1"),
        entry_price=Decimal("45000"),
        current_price=Decimal("46000"),
        unrealized_pnl=Decimal("100"),
        unrealized_pnl_percentage=Decimal("2.22"),
        value=Decimal("4600")
    )

    position2 = Position(
        symbol="ETH/USDT",
        side=OrderSide.BUY,
        amount=Decimal("1.0"),
        entry_price=Decimal("2500"),
        current_price=Decimal("2600"),
        unrealized_pnl=Decimal("100"),
        unrealized_pnl_percentage=Decimal("4.00"),
        value=Decimal("2600")
    )

    portfolio = Portfolio(
        timestamp=1704067200000,
        dt=datetime.now(timezone.utc),
        total_value=Decimal("17200"),
        cash=Decimal("10000"),
        positions=[position1, position2]
    )

    # Test getting existing position
    btc_position = portfolio.get_position("BTC/USDT")
    assert btc_position is not None
    assert btc_position.symbol == "BTC/USDT"

    # Test getting non-existing position
    non_exist = portfolio.get_position("SOL/USDT")
    assert non_exist is None


def test_portfolio_get_allocation():
    """Test getting allocation percentage"""
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

    portfolio = Portfolio(
        timestamp=1704067200000,
        dt=datetime.now(timezone.utc),
        total_value=Decimal("10000"),
        cash=Decimal("5400"),
        positions=[position]
    )

    # Position value is 4600, total is 10000
    # Allocation should be 46%
    allocation = portfolio.get_allocation("BTC/USDT")
    assert allocation == Decimal("46")

    # Non-existing position should return 0
    allocation_non_exist = portfolio.get_allocation("ETH/USDT")
    assert allocation_non_exist == Decimal("0")


def test_portfolio_allocation_zero_total():
    """Test allocation when total value is zero"""
    portfolio = Portfolio(
        timestamp=1704067200000,
        dt=datetime.now(timezone.utc),
        total_value=Decimal("0"),
        cash=Decimal("0"),
        positions=[]
    )

    allocation = portfolio.get_allocation("BTC/USDT")
    assert allocation == Decimal("0")


def test_portfolio_with_pnl():
    """Test portfolio with PnL values"""
    portfolio = Portfolio(
        timestamp=1704067200000,
        dt=datetime.now(timezone.utc),
        total_value=Decimal("15500"),
        cash=Decimal("10000"),
        positions=[],
        total_pnl=Decimal("500"),
        daily_pnl=Decimal("100"),
        total_return=Decimal("3.33")
    )

    assert portfolio.total_pnl == Decimal("500")
    assert portfolio.daily_pnl == Decimal("100")
    assert portfolio.total_return == Decimal("3.33")
