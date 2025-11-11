from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import List
from unittest.mock import AsyncMock

import pytest

from src.decision.llm_client import LLMResponse
from src.learning.reflection import LLMReflectionEngine
from src.models.memory import TradingExperience
from src.models.performance import PerformanceMetrics


pytestmark = pytest.mark.asyncio


def _make_experience(outcome: str = "success", tags: List[str] | None = None) -> TradingExperience:
    now = datetime.now(timezone.utc)
    return TradingExperience(
        id="exp-1",
        timestamp=int(now.timestamp() * 1000),
        dt=now,
        situation="市场快速拉升",
        situation_embedding=None,
        decision="追多突破",
        decision_reasoning="突破区间上沿",
        outcome=outcome,
        pnl=Decimal("150"),
        pnl_percentage=Decimal("3"),
        reflection=None,
        lessons_learned=["突破后缩量回落要注意"],
        tags=tags or ["breakout"],
        importance_score=0.8,
    )


def _make_performance() -> PerformanceMetrics:
    now = datetime.now(timezone.utc)
    return PerformanceMetrics(
        start_date=now,
        end_date=now,
        total_return=Decimal("12"),
        annualized_return=Decimal("36"),
        daily_returns=[Decimal("0.01"), Decimal("-0.005"), Decimal("0.02")],
        volatility=Decimal("0.15"),
        max_drawdown=Decimal("6"),
        sharpe_ratio=Decimal("1.3"),
        sortino_ratio=Decimal("1.1"),
        calmar_ratio=Decimal("2.0"),
        total_trades=20,
        winning_trades=12,
        losing_trades=8,
        win_rate=Decimal("0.6"),
        avg_win=Decimal("80"),
        avg_loss=Decimal("50"),
        profit_factor=Decimal("1.4"),
        max_consecutive_wins=4,
        max_consecutive_losses=3,
    )


async def test_reflect_on_trade_fallback():
    engine = LLMReflectionEngine()
    exp = _make_experience(outcome="failure")
    result = await engine.reflect_on_trade(exp)
    assert "交易" in result
    assert "failure" in result


async def test_reflect_on_trade_with_llm():
    mock_llm = AsyncMock()
    mock_llm.chat.return_value = LLMResponse(
        content="LLM输出反思",
        tool_calls=None,
        finish_reason="stop",
        tokens_used=50,
        model="mock-llm",
    )
    engine = LLMReflectionEngine(mock_llm)
    exp = _make_experience(outcome="success")
    result = await engine.reflect_on_trade(exp)
    assert result == "LLM输出反思"
    mock_llm.chat.assert_awaited()


async def test_reflect_on_period_fallback():
    engine = LLMReflectionEngine()
    performance = _make_performance()
    result = await engine.reflect_on_period(performance)
    assert "summary" in result
    assert isinstance(result["strengths"], list)


async def test_identify_patterns_fallback():
    engine = LLMReflectionEngine()
    exp1 = _make_experience("success", ["swing"])
    exp2 = _make_experience("failure", ["swing"])
    exp3 = _make_experience("success", ["breakout"])

    patterns = await engine.identify_patterns([exp1, exp2, exp3])
    assert patterns
    swing_pattern = next((p for p in patterns if p["pattern"] == "swing"), None)
    assert swing_pattern is not None
    assert swing_pattern["frequency"] == 2
