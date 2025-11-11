from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict
from unittest.mock import AsyncMock, Mock

import pytest

from src.decision.llm_client import LLMResponse, ToolCall
from src.decision.tools import ToolRegistry
from src.decision.trader import LLMTrader
from src.models.decision import SignalType, StrategyConfig, TradingSignal
from src.models.portfolio import Portfolio
from src.models.trade import OrderSide, Position


pytestmark = pytest.mark.asyncio


def _strategy() -> StrategyConfig:
    now = datetime.now(tz=timezone.utc)
    return StrategyConfig(
        name="adaptive",
        version="1.0",
        description="Adaptive strategy",
        max_position_size=Decimal("0.2"),
        max_single_trade=Decimal("2000"),
        max_open_positions=3,
        max_daily_loss=Decimal("0.05"),
        max_drawdown=Decimal("0.15"),
        stop_loss_percentage=Decimal("5"),
        take_profit_percentage=Decimal("10"),
        trading_pairs=["BTC/USDT"],
        timeframes=["1h", "4h"],
        updated_at=now,
        reason_for_update="Initial setup",
    )


def _portfolio() -> Portfolio:
    now = datetime.now(tz=timezone.utc)
    position = Position(
        symbol="BTC/USDT",
        side=OrderSide.BUY,
        amount=Decimal("0.1"),
        entry_price=Decimal("40000"),
        current_price=Decimal("41000"),
        unrealized_pnl=Decimal("100"),
        unrealized_pnl_percentage=Decimal("2.5"),
        value=Decimal("4100"),
        stop_loss=None,
        take_profit=None,
    )
    return Portfolio(
        timestamp=int(now.timestamp() * 1000),
        dt=now,
        total_value=Decimal("50000"),
        cash=Decimal("20000"),
        positions=[position],
        total_pnl=Decimal("1500"),
        daily_pnl=Decimal("200"),
        total_return=Decimal("5"),
    )


async def test_generate_trading_signal_returns_model():
    llm = AsyncMock()
    llm.chat.return_value = LLMResponse(
        content=(
            '{"signal_type": "enter_long", "confidence": 0.7, "suggested_price": 40500, '
            '"stop_loss": 39000, "take_profit": 43000, '
            '"factors": {"supporting": ["Breakout"], "risks": ["Volatility"]}}'
        ),
        tool_calls=None,
        finish_reason="stop",
        tokens_used=8,
        model="deepseek-chat",
    )

    trader = LLMTrader(llm, tool_registry=None, memory_retrieval=None)
    signal = await trader.generate_trading_signal("BTC/USDT", _strategy())

    assert isinstance(signal, TradingSignal)
    assert signal.signal_type == SignalType.ENTER_LONG
    assert signal.stop_loss == Decimal("39000")
    assert "Breakout" in signal.supporting_factors


async def test_calculate_position_size_applies_constraints():
    llm = AsyncMock()
    llm.chat.return_value = LLMResponse(
        content='{"signal_type": "hold"}',
        tool_calls=None,
        finish_reason="stop",
        tokens_used=1,
        model="deepseek-chat",
    )

    trader = LLMTrader(llm, tool_registry=None, memory_retrieval=None)
    signal = TradingSignal(
        timestamp=0,
        dt=datetime.now(tz=timezone.utc),
        symbol="BTC/USDT",
        signal_type=SignalType.ENTER_LONG,
        confidence=0.6,
        suggested_price=Decimal("40000"),
        suggested_amount=None,
        stop_loss=Decimal("38000"),
        take_profit=None,
        reasoning="",
        supporting_factors=[],
        risk_factors=[],
        source="trader",
    )

    position_size = await trader.calculate_position_size(
        signal,
        _portfolio(),
        {
            "max_position_size": Decimal("0.2"),
            "max_daily_loss": Decimal("0.05"),
            "stop_loss_percentage": Decimal("5"),
            "max_single_trade": Decimal("3000"),
        },
    )

    assert position_size > 0
    assert position_size < Decimal("1")


async def test_trader_tool_call_executes_registry():
    llm = AsyncMock()
    first = LLMResponse(
        content="investigate",
        tool_calls=[
            ToolCall(
                id="tool_1",
                name="market_data_query",
                arguments={"symbol": "BTC/USDT"},
            )
        ],
        finish_reason="tool_calls",
        tokens_used=4,
        model="deepseek-chat",
    )
    second = LLMResponse(
        content='{"signal_type": "hold"}',
        tool_calls=None,
        finish_reason="stop",
        tokens_used=2,
        model="deepseek-chat",
    )
    llm.chat.side_effect = [first, second]

    registry = ToolRegistry()
    registry.get_all_schemas = Mock(return_value=[{"type": "function", "function": {"name": "market_data_query", "parameters": {"type": "object", "properties": {}, "required": []}}}])

    executed: Dict[str, Any] = {}

    async def fake_execute(name: str, **kwargs: Any) -> Dict[str, Any]:
        executed["name"] = name
        executed["kwargs"] = kwargs
        return {"price": 42000}

    registry.execute_tool = AsyncMock(side_effect=fake_execute)

    trader = LLMTrader(llm, tool_registry=registry, memory_retrieval=None)
    signal = await trader.generate_trading_signal("BTC/USDT", _strategy())

    assert signal.signal_type == SignalType.HOLD
    registry.execute_tool.assert_awaited_once()
    assert executed["kwargs"] == {"symbol": "BTC/USDT"}
