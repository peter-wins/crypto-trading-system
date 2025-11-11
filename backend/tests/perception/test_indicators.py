"""Tests for indicator calculator"""

import pytest
from decimal import Decimal

from src.perception.indicators import PandasIndicatorCalculator


@pytest.fixture
def calculator():
    """Create indicator calculator instance"""
    return PandasIndicatorCalculator()


@pytest.fixture
def sample_prices():
    """Sample price data for testing"""
    return [
        Decimal("100"), Decimal("102"), Decimal("101"), Decimal("103"),
        Decimal("105"), Decimal("104"), Decimal("106"), Decimal("108"),
        Decimal("107"), Decimal("109"), Decimal("111"), Decimal("110"),
        Decimal("112"), Decimal("114"), Decimal("113"), Decimal("115"),
        Decimal("117"), Decimal("116"), Decimal("118"), Decimal("120")
    ]


def test_calculate_sma(calculator, sample_prices):
    """Test SMA calculation"""
    sma = calculator.calculate_sma(sample_prices, 5)

    assert len(sma) == len(sample_prices)
    # SMA should smooth out the data
    assert sma[0] == Decimal("0")  # Not enough data
    assert sma[4] > Decimal("0")  # Has enough data


def test_calculate_ema(calculator, sample_prices):
    """Test EMA calculation"""
    ema = calculator.calculate_ema(sample_prices, 5)

    assert len(ema) == len(sample_prices)
    # EMA reacts faster than SMA
    assert ema[-1] != Decimal("0")


def test_calculate_rsi(calculator, sample_prices):
    """Test RSI calculation"""
    rsi = calculator.calculate_rsi(sample_prices, 14)

    assert len(rsi) == len(sample_prices)
    # RSI should be between 0 and 100
    for value in rsi:
        assert Decimal("0") <= value <= Decimal("100")


def test_calculate_macd(calculator, sample_prices):
    """Test MACD calculation"""
    macd = calculator.calculate_macd(sample_prices)

    assert "macd" in macd
    assert "signal" in macd
    assert "histogram" in macd
    assert len(macd["macd"]) == len(sample_prices)


def test_calculate_bollinger_bands(calculator, sample_prices):
    """Test Bollinger Bands calculation"""
    bbands = calculator.calculate_bollinger_bands(sample_prices, 10)

    assert "upper" in bbands
    assert "middle" in bbands
    assert "lower" in bbands
    assert len(bbands["upper"]) == len(sample_prices)

    # Upper should be >= middle >= lower
    for i in range(len(sample_prices)):
        if bbands["upper"][i] != Decimal("0"):
            assert bbands["upper"][i] >= bbands["middle"][i]
            assert bbands["middle"][i] >= bbands["lower"][i]


def test_calculate_atr(calculator, sample_prices):
    """Test ATR calculation"""
    high = [p + Decimal("2") for p in sample_prices]
    low = [p - Decimal("2") for p in sample_prices]

    atr = calculator.calculate_atr(high, low, sample_prices, 14)

    assert len(atr) == len(sample_prices)
    # ATR should be positive
    for value in atr:
        assert value >= Decimal("0")


def test_calculate_stochastic(calculator, sample_prices):
    """Test Stochastic indicator calculation"""
    high = [p + Decimal("2") for p in sample_prices]
    low = [p - Decimal("2") for p in sample_prices]

    stoch = calculator.calculate_stochastic(high, low, sample_prices)

    assert "k" in stoch
    assert "d" in stoch
    assert len(stoch["k"]) == len(sample_prices)

    # Stochastic should be between 0 and 100
    for k, d in zip(stoch["k"], stoch["d"]):
        assert Decimal("0") <= k <= Decimal("100")
        assert Decimal("0") <= d <= Decimal("100")


def test_calculate_obv(calculator, sample_prices):
    """Test OBV calculation"""
    volume = [Decimal("1000") for _ in sample_prices]

    obv = calculator.calculate_obv(sample_prices, volume)

    assert len(obv) == len(sample_prices)


def test_calculate_all_indicators(calculator, sample_prices):
    """Test calculating all indicators at once"""
    high = [p + Decimal("2") for p in sample_prices]
    low = [p - Decimal("2") for p in sample_prices]
    volume = [Decimal("1000") for _ in sample_prices]

    indicators = calculator.calculate_all_indicators(high, low, sample_prices, volume)

    assert "sma_20" in indicators
    assert "ema_12" in indicators
    assert "rsi_14" in indicators
    assert "macd" in indicators
    assert "bollinger" in indicators
    assert "atr_14" in indicators
    assert "obv" in indicators
