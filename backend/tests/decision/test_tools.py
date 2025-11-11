from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from src.decision.tools import (
    MarketDataQueryTool,
    MemorySearchTool,
    RiskCalculatorTool,
    TechnicalAnalysisTool,
    ToolRegistry,
)
from src.models.market import OHLCVData, Ticker
from src.models.memory import TradingExperience


pytestmark = pytest.mark.asyncio


def _make_candle(price: float, timestamp: int) -> OHLCVData:
    return OHLCVData(
        symbol="BTC/USDT",
        timestamp=timestamp,
        dt=datetime.fromtimestamp(timestamp / 1000),
        open=Decimal(str(price)),
        high=Decimal(str(price + 10)),
        low=Decimal(str(price - 10)),
        close=Decimal(str(price)),
        volume=Decimal("100"),
    )


async def test_market_data_query_tool_returns_ticker():
    ticker = Ticker(
        symbol="BTC/USDT",
        timestamp=123456789,
        dt=datetime.now(timezone.utc),
        last=Decimal("42000"),
        bid=Decimal("41990"),
        ask=Decimal("42005"),
        high=Decimal("43000"),
        low=Decimal("41000"),
        volume=Decimal("1200"),
        quote_volume=Decimal("50000000"),
        change_24h=Decimal("5.1"),
    )
    collector = AsyncMock()
    collector.get_ticker.return_value = ticker

    tool = MarketDataQueryTool(collector)
    result = await tool.execute(symbol="BTC/USDT")

    assert result["price"] == pytest.approx(42000)
    collector.get_ticker.assert_awaited_once()


async def test_market_data_query_tool_returns_ohlcv():
    candles = [_make_candle(40000 + idx, 1700000000000 + idx * 3600 * 1000) for idx in range(3)]
    collector = AsyncMock()
    collector.get_ohlcv.return_value = candles

    tool = MarketDataQueryTool(collector)
    result = await tool.execute(symbol="BTC/USDT", data_type="ohlcv", timeframe="1h", limit=3)

    assert len(result["data"]) == 3
    collector.get_ohlcv.assert_awaited_once()


async def test_technical_analysis_tool_uses_indicator_calculator():
    candles = [_make_candle(40000 + idx, 1700000000000 + idx * 3600 * 1000) for idx in range(200)]
    collector = AsyncMock()
    collector.get_ohlcv.return_value = candles

    indicator = Mock()
    indicator.calculate_rsi.return_value = [Decimal("50")] * len(candles)
    indicator.calculate_macd.return_value = {
        "macd": [Decimal("1")] * len(candles),
        "signal": [Decimal("0.5")] * len(candles),
        "histogram": [Decimal("0.3")] * len(candles),
    }
    indicator.calculate_sma.return_value = [Decimal("40000")] * len(candles)
    indicator.calculate_ema.return_value = [Decimal("40000")] * len(candles)
    indicator.calculate_bollinger_bands.return_value = {
        "upper": [Decimal("41000")] * len(candles),
        "middle": [Decimal("40000")] * len(candles),
        "lower": [Decimal("39000")] * len(candles),
    }

    tool = TechnicalAnalysisTool(collector, indicator)
    result = await tool.execute(symbol="BTC/USDT", indicators=["rsi", "macd", "sma", "bollinger"])

    assert "rsi" in result["indicators"]
    assert result["indicators"]["macd"]["interpretation"] == "bullish"
    indicator.calculate_rsi.assert_called()


async def test_memory_search_tool_uses_retrieval():
    memory = AsyncMock()
    experience = TradingExperience(
        id="1",
        timestamp=123,
        dt=datetime.now(timezone.utc),
        situation="Volatile market",
        situation_embedding=None,
        decision="Reduce exposure",
        decision_reasoning="High volatility",
        outcome="success",
        pnl=Decimal("100"),
        pnl_percentage=Decimal("1.5"),
        reflection="",
        lessons_learned=["Manage risk"],
        tags=["risk"],
        importance_score=0.9,
    )
    memory.search_similar_experiences.return_value = [experience]

    tool = MemorySearchTool(memory)
    result = await tool.execute(query="High volatility", top_k=1)

    assert result["results"][0]["decision"] == "Reduce exposure"
    memory.search_similar_experiences.assert_awaited()


async def test_risk_calculator_tool_outputs_expected_values():
    tool = RiskCalculatorTool()
    result = await tool.execute(entry_price=20000, stop_loss_pct=5, risk_amount=500)

    assert pytest.approx(result["stop_loss_price"], rel=1e-3) == 19000
    assert pytest.approx(result["position_size"], rel=1e-3) == 0.5


async def test_tool_registry_executes_registered_tool():
    tool = RiskCalculatorTool()
    registry = ToolRegistry()
    registry.register(tool)

    output = await registry.execute_tool(
        "risk_calculator",
        entry_price=20000,
        stop_loss_pct=5,
        risk_amount=500,
    )

    assert "take_profit_price" in output
