from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import List

import pytest

from src.memory.retrieval import RAGMemoryRetrieval
from src.models.memory import MarketContext, MemoryQuery, TradingContext, TradingExperience
from src.models.portfolio import Portfolio
from src.models.trade import OrderSide, Position


pytestmark = pytest.mark.asyncio


class FakeShortTermMemory:
    def __init__(self, market_context: MarketContext, trading_context: TradingContext) -> None:
        self._market = market_context
        self._trading = trading_context

    async def get_market_context(self, symbol: str):
        return self._market

    async def update_market_context(self, symbol: str, context: MarketContext):
        self._market = context
        return True

    async def get_trading_context(self):
        return self._trading

    async def update_trading_context(self, context: TradingContext):
        self._trading = context
        return True


class FakeLongTermMemory:
    def __init__(self, experiences: List[TradingExperience]):
        self.experiences = experiences
        self.queries: List[MemoryQuery] = []

    async def search_similar_experiences(self, query: MemoryQuery):
        self.queries.append(query)
        return self.experiences[: query.top_k]


def _make_market_context(symbol: str) -> MarketContext:
    now = datetime.now(timezone.utc)
    return MarketContext(
        timestamp=int(now.timestamp() * 1000),
        dt=now,
        market_regime="bull",
        volatility=Decimal("0.15"),
        trend="up",
        recent_prices=[Decimal("100"), Decimal("101"), Decimal("102")],
        indicators={"rsi": 55, "macd": "bullish"},
        recent_trades=[f"{symbol}-trade"],
    )


def _make_trading_context(symbol: str, market_context: MarketContext) -> TradingContext:
    now = datetime.now(timezone.utc)
    portfolio = Portfolio(
        timestamp=int(now.timestamp() * 1000),
        dt=now,
        total_value=Decimal("20000"),
        cash=Decimal("5000"),
        positions=[
            Position(
                symbol=symbol,
                side=OrderSide.BUY,
                amount=Decimal("0.5"),
                entry_price=Decimal("30000"),
                current_price=Decimal("32000"),
                unrealized_pnl=Decimal("1000"),
                unrealized_pnl_percentage=Decimal("3"),
                value=Decimal("16000"),
                stop_loss=None,
                take_profit=None,
            )
        ],
        total_pnl=Decimal("1500"),
        daily_pnl=Decimal("200"),
        total_return=Decimal("7.5"),
    )
    return TradingContext(
        timestamp=int(now.timestamp() * 1000),
        dt=now,
        current_strategy="swing",
        strategy_params={"window": 14},
        max_position_size=Decimal("0.25"),
        max_daily_loss=Decimal("0.04"),
        current_daily_loss=Decimal("0.01"),
        market_context=market_context,
        portfolio=portfolio,
    )


def _make_experience(exp_id: str) -> TradingExperience:
    now = datetime.now(timezone.utc)
    return TradingExperience(
        id=exp_id,
        timestamp=int(now.timestamp() * 1000),
        dt=now,
        situation="BTC breakout during bull trend",
        situation_embedding=None,
        decision="Enter long",
        decision_reasoning="RSI breakout",
        outcome="success",
        pnl=Decimal("300"),
        pnl_percentage=Decimal("4.5"),
        reflection="",
        lessons_learned=["Follow trend"],
        tags=["trend"],
        importance_score=0.9,
    )


@pytest.fixture
def retrieval_components():
    symbol = "BTC/USDT"
    market_context = _make_market_context(symbol)
    trading_context = _make_trading_context(symbol, market_context)
    experiences = [_make_experience("exp-1"), _make_experience("exp-2")]

    short_term = FakeShortTermMemory(market_context, trading_context)
    long_term = FakeLongTermMemory(experiences)
    retrieval = RAGMemoryRetrieval(short_term, long_term, default_top_k=2)
    return retrieval, short_term, long_term, symbol


@pytest.mark.asyncio
async def test_retrieve_relevant_context(retrieval_components):
    retrieval, _, long_term, symbol = retrieval_components

    context = await retrieval.retrieve_relevant_context(f"Situation for {symbol}", top_k=1)

    assert len(context["similar_experiences"]) == 1
    assert context["current_context"].current_strategy == "swing"
    assert context["market_context"].market_regime == "bull"
    assert long_term.queries[0].top_k == 1


@pytest.mark.asyncio
async def test_build_context_for_llm_contains_sections(retrieval_components):
    retrieval, _, long_term, symbol = retrieval_components

    prompt = await retrieval.build_context_for_llm(symbol, "strategic")

    assert "=== 市场上下文 ===" in prompt
    assert "=== 交易上下文 ===" in prompt
    assert "=== 相似经验 ===" in prompt
    assert "Follow trend" in prompt
    assert long_term.queries[-1].filters.get("outcome") == "success"
