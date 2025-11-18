"""Tests for market data models"""

import pytest
from datetime import datetime, timezone
from decimal import Decimal

from src.models.market import OHLCVData, OrderBook, OrderBookLevel, Ticker


def test_ohlcv_data_creation():
    """Test OHLCV data model creation"""
    ohlcv = OHLCVData(
        symbol="BTC/USDT",
        timestamp=1704067200000,
        dt=datetime.now(timezone.utc),
        open=Decimal("45000.50"),
        high=Decimal("45500.00"),
        low=Decimal("44800.00"),
        close=Decimal("45200.00"),
        volume=Decimal("123.456")
    )

    assert ohlcv.symbol == "BTC/USDT"
    assert ohlcv.open == Decimal("45000.50")
    assert ohlcv.high == Decimal("45500.00")
    assert ohlcv.low == Decimal("44800.00")
    assert ohlcv.close == Decimal("45200.00")
    assert ohlcv.volume == Decimal("123.456")


def test_order_book_level():
    """Test order book level model"""
    level = OrderBookLevel(
        price=Decimal("45000"),
        amount=Decimal("1.5")
    )

    assert level.price == Decimal("45000")
    assert level.amount == Decimal("1.5")


def test_order_book_spread():
    """Test order book spread calculation"""
    order_book = OrderBook(
        symbol="BTC/USDT",
        timestamp=1704067200000,
        dt=datetime.now(timezone.utc),
        bids=[
            OrderBookLevel(price=Decimal("45000"), amount=Decimal("1.5")),
            OrderBookLevel(price=Decimal("44990"), amount=Decimal("2.0"))
        ],
        asks=[
            OrderBookLevel(price=Decimal("45010"), amount=Decimal("1.0")),
            OrderBookLevel(price=Decimal("45020"), amount=Decimal("1.5"))
        ]
    )

    spread = order_book.get_spread()
    assert spread == Decimal("10")  # 45010 - 45000


def test_order_book_mid_price():
    """Test order book mid price calculation"""
    order_book = OrderBook(
        symbol="BTC/USDT",
        timestamp=1704067200000,
        dt=datetime.now(timezone.utc),
        bids=[
            OrderBookLevel(price=Decimal("45000"), amount=Decimal("1.5"))
        ],
        asks=[
            OrderBookLevel(price=Decimal("45010"), amount=Decimal("1.0"))
        ]
    )

    mid_price = order_book.get_mid_price()
    assert mid_price == Decimal("45005")  # (45000 + 45010) / 2


def test_order_book_empty():
    """Test order book with empty bids/asks"""
    order_book = OrderBook(
        symbol="BTC/USDT",
        timestamp=1704067200000,
        dt=datetime.now(timezone.utc),
        bids=[],
        asks=[]
    )

    assert order_book.get_spread() == Decimal("0")
    assert order_book.get_mid_price() == Decimal("0")


def test_ticker_creation():
    """Test ticker model creation"""
    ticker = Ticker(
        symbol="BTC/USDT",
        timestamp=1704067200000,
        dt=datetime.now(timezone.utc),
        last=Decimal("45200"),
        bid=Decimal("45190"),
        ask=Decimal("45210"),
        high=Decimal("46000"),
        low=Decimal("44000"),
        volume=Decimal("1234.567"),
        quote_volume=Decimal("55555555.00"),
        change_24h=Decimal("2.5")
    )

    assert ticker.symbol == "BTC/USDT"
    assert ticker.last == Decimal("45200")
    assert ticker.bid == Decimal("45190")
    assert ticker.ask == Decimal("45210")
    assert ticker.change_24h == Decimal("2.5")
