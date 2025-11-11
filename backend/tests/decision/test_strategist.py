from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict
from unittest.mock import AsyncMock, Mock

import pytest

from src.decision.llm_client import LLMResponse, Message, ToolCall
from src.decision.strategist import LLMStrategist
from src.decision.tools import ToolRegistry
from src.models.decision import StrategyConfig
from src.models.performance import PerformanceMetrics
from src.models.portfolio import Portfolio
from src.models.trade import OrderSide, Position


pytestmark = pytest.mark.asyncio


def _portfolio() -> Portfolio:
    now = datetime.now(tz=timezone.utc)
    position = Position(
        symbol="BTC/USDT",
        side=OrderSide.BUY,
        amount=Decimal("0.5"),
        entry_price=Decimal("40000"),
        current_price=Decimal("42000"),
        unrealized_pnl=Decimal("1000"),
        unrealized_pnl_percentage=Decimal("2.5"),
        value=Decimal("21000"),
        stop_loss=None,
        take_profit=None,
    )
    return Portfolio(
        timestamp=int(now.timestamp() * 1000),
        dt=now,
        total_value=Decimal("50000"),
        cash=Decimal("25000"),
        positions=[position],
        total_pnl=Decimal("2000"),
        daily_pnl=Decimal("500"),
        total_return=Decimal("10"),
    )


async def test_analyze_market_regime_parses_response():
    llm = AsyncMock()
    llm.chat.return_value = LLMResponse(
        content='{"regime": "bull", "confidence": 0.8, "key_factors": ["trend"], "reasoning": "Strong momentum"}',
        tool_calls=None,
        finish_reason="stop",
        tokens_used=10,
        model="deepseek-chat",
    )

    strategist = LLMStrategist(llm, memory_retrieval=None, tool_registry=None)
    result = await strategist.analyze_market_regime("BTC/USDT")

    assert result["regime"] == "bull"
    assert result["confidence"] == pytest.approx(0.8)
    llm.chat.assert_awaited_once()


async def test_make_strategic_decision_creates_config():
    llm = AsyncMock()
    llm.chat.return_value = LLMResponse(
        content=(
            '{"strategy": {"name": "momentum", "version": "1.1", "timeframes": ["1h"]}, '
            '"risk_parameters": {"max_position_size": 0.3, "max_single_trade": 2000, '
            '"max_daily_loss": 0.04, "max_drawdown": 0.1, "stop_loss_percentage": 4, '
            '"take_profit_percentage": 8}, "reasoning": "Updated for momentum"}'
        ),
        tool_calls=None,
        finish_reason="stop",
        tokens_used=12,
        model="deepseek-chat",
    )

    strategist = LLMStrategist(llm, memory_retrieval=None, tool_registry=None)
    portfolio = _portfolio()
    strategy = await strategist.make_strategic_decision(portfolio)

    assert isinstance(strategy, StrategyConfig)
    assert strategy.name == "momentum"
    assert strategy.max_position_size == Decimal("0.3")
    assert strategy.take_profit_percentage == Decimal("8")


async def test_tool_call_flow_executes_registered_tool():
    llm = AsyncMock()
    first_response = LLMResponse(
        content="need data",
        tool_calls=[
            ToolCall(
                id="call_1",
                name="market_data_query",
                arguments={"symbol": "BTC/USDT"},
            )
        ],
        finish_reason="tool_calls",
        tokens_used=5,
        model="deepseek-chat",
    )
    final_response = LLMResponse(
        content='{"strategy": {"name": "adaptive", "version": "1.0"}, "risk_parameters": {"max_position_size": 0.2}}',
        tool_calls=None,
        finish_reason="stop",
        tokens_used=8,
        model="deepseek-chat",
    )
    llm.chat.side_effect = [first_response, final_response]

    registry = ToolRegistry()
    registry.get_all_schemas = Mock(return_value=[{"type": "function", "function": {"name": "market_data_query", "parameters": {"type": "object", "properties": {}, "required": []}}}])

    executed: Dict[str, Any] = {}

    async def fake_execute(name: str, **kwargs: Any) -> Dict[str, Any]:
        executed["name"] = name
        executed["kwargs"] = kwargs
        return {"price": 42000}

    registry.execute_tool = AsyncMock(side_effect=fake_execute)

    strategist = LLMStrategist(llm, memory_retrieval=None, tool_registry=registry)
    strategy = await strategist.make_strategic_decision(_portfolio())

    assert strategy.name == "adaptive"
    registry.execute_tool.assert_awaited_once()
    assert executed["kwargs"] == {"symbol": "BTC/USDT"}


async def test_update_risk_parameters_returns_decimal_map():
    llm = AsyncMock()
    llm.chat.return_value = LLMResponse(
        content='{"max_position_size": 0.25, "max_daily_loss": 0.05}',
        tool_calls=None,
        finish_reason="stop",
        tokens_used=6,
        model="deepseek-chat",
    )

    strategist = LLMStrategist(llm, memory_retrieval=None, tool_registry=None)
    now = datetime.now(tz=timezone.utc)
    performance = PerformanceMetrics(
        start_date=now,
        end_date=now,
        total_return=Decimal("12"),
        annualized_return=Decimal("20"),
        daily_returns=[Decimal("0.5")],
        volatility=Decimal("0.2"),
        max_drawdown=Decimal("0.1"),
        sharpe_ratio=Decimal("1.5"),
        sortino_ratio=Decimal("1.2"),
        calmar_ratio=Decimal("1.1"),
        total_trades=10,
        winning_trades=6,
        losing_trades=4,
        win_rate=Decimal("0.6"),
        avg_win=Decimal("200"),
        avg_loss=Decimal("100"),
        profit_factor=Decimal("2"),
        max_consecutive_wins=3,
        max_consecutive_losses=2,
    )

    result = await strategist.update_risk_parameters(performance)
    assert result["max_position_size"] == Decimal("0.25")
    assert result["max_daily_loss"] == Decimal("0.05")
