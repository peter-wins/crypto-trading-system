from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from fnmatch import fnmatch
from typing import Any, Dict, List, Optional

import pytest

from src.memory.short_term import RedisShortTermMemory
from src.models.memory import MarketContext, TradingContext
from src.models.portfolio import Portfolio
from src.models.trade import OrderSide, Position


pytestmark = pytest.mark.asyncio


class FakeRedis:
    """Minimal async Redis stub for unit tests."""

    def __init__(self) -> None:
        self.store: Dict[str, str] = {}
        self.ttl_map: Dict[str, int] = {}

    async def ping(self) -> bool:
        return True

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self.store[key] = value
        self.ttl_map[key] = ttl

    async def set(self, key: str, value: str) -> None:
        self.store[key] = value
        self.ttl_map.pop(key, None)

    async def get(self, key: str) -> Optional[str]:
        return self.store.get(key)

    async def delete(self, key: str) -> int:
        existed = key in self.store
        self.store.pop(key, None)
        self.ttl_map.pop(key, None)
        return int(existed)

    async def exists(self, key: str) -> int:
        return int(key in self.store)

    async def ttl(self, key: str) -> int:
        if key not in self.store:
            return -2
        return self.ttl_map.get(key, -1)

    async def expire(self, key: str, ttl: int) -> bool:
        if key in self.store:
            self.ttl_map[key] = ttl
            return True
        return False

    async def mget(self, keys: List[str]) -> List[Optional[str]]:
        return [self.store.get(key) for key in keys]

    async def flushdb(self) -> None:
        self.store.clear()
        self.ttl_map.clear()

    async def aclose(self) -> None:
        return None

    async def scan_iter(self, match: str | None = None):
        for key in list(self.store.keys()):
            if match is None or fnmatch(key, match):
                yield key

    def pipeline(self):
        return FakePipeline(self)


class FakePipeline:
    """Async pipeline that defers execution until execute()."""

    def __init__(self, redis_client: FakeRedis) -> None:
        self.redis = redis_client
        self.operations: List[tuple] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def setex(self, key: str, ttl: int, value: str):
        self.operations.append(("setex", key, ttl, value))
        return self

    def set(self, key: str, value: str):
        self.operations.append(("set", key, value))
        return self

    async def execute(self):
        for op in self.operations:
            if op[0] == "setex":
                await self.redis.setex(op[1], op[2], op[3])
            else:
                await self.redis.set(op[1], op[2])
        self.operations.clear()
        return True


@pytest.fixture
def fake_redis(monkeypatch):
    client = FakeRedis()
    async def _from_url(*args, **kwargs):  # pragma: no cover - simple stub
        return client

    monkeypatch.setattr("redis.asyncio.from_url", _from_url)
    return client


def _make_market_context(symbol: str) -> MarketContext:
    now = datetime.now(timezone.utc)
    return MarketContext(
        timestamp=int(now.timestamp() * 1000),
        dt=now,
        market_regime="bull",
        volatility=Decimal("0.12"),
        trend="up",
        recent_prices=[Decimal("100"), Decimal("101"), Decimal("102")],
        indicators={"rsi": 55},
        recent_trades=[f"{symbol}-trade"],
    )


def _make_trading_context(symbol: str) -> TradingContext:
    now = datetime.now(timezone.utc)
    market_context = _make_market_context(symbol)
    portfolio = Portfolio(
        timestamp=int(now.timestamp() * 1000),
        dt=now,
        total_value=Decimal("10000"),
        cash=Decimal("4000"),
        positions=[
            Position(
                symbol=symbol,
                side=OrderSide.BUY,
                amount=Decimal("0.5"),
                entry_price=Decimal("18000"),
                current_price=Decimal("20000"),
                unrealized_pnl=Decimal("1000"),
                unrealized_pnl_percentage=Decimal("5"),
                value=Decimal("10000"),
                stop_loss=None,
                take_profit=None,
            )
        ],
        total_pnl=Decimal("500"),
        daily_pnl=Decimal("200"),
        total_return=Decimal("5"),
    )
    return TradingContext(
        timestamp=int(now.timestamp() * 1000),
        dt=now,
        current_strategy="trend_following",
        strategy_params={"lookback": 20},
        max_position_size=Decimal("0.2"),
        max_daily_loss=Decimal("0.05"),
        current_daily_loss=Decimal("0.01"),
        market_context=market_context,
        portfolio=portfolio,
    )


@pytest.mark.asyncio
async def test_update_and_get_market_context(fake_redis):
    memory = RedisShortTermMemory()
    context = _make_market_context("BTC/USDT")

    assert await memory.update_market_context("BTC/USDT", context)
    stored = await memory.get_market_context("BTC/USDT")

    assert stored is not None
    assert stored.market_regime == "bull"
    assert await memory.get_ttl("market:context:BTC/USDT") == memory.MARKET_CONTEXT_TTL


@pytest.mark.asyncio
async def test_update_and_get_trading_context(fake_redis):
    memory = RedisShortTermMemory()
    context = _make_trading_context("BTC/USDT")

    assert await memory.update_trading_context(context)
    stored = await memory.get_trading_context()

    assert stored is not None
    assert stored.current_strategy == "trend_following"
    assert stored.market_context.market_regime == "bull"
    assert await memory.get_ttl(memory.TRADING_CONTEXT_KEY) == memory.TRADING_CONTEXT_TTL


@pytest.mark.asyncio
async def test_set_and_get_generic_value(fake_redis):
    memory = RedisShortTermMemory()
    assert await memory.set("custom:key", {"foo": "bar"}, ttl=120)

    retrieved = await memory.get("custom:key")
    assert retrieved == {"foo": "bar"}
    assert await memory.exists("custom:key")
    assert await memory.get_ttl("custom:key") == 120


@pytest.mark.asyncio
async def test_get_keys_by_pattern(fake_redis):
    memory = RedisShortTermMemory()
    await memory.set("market:context:BTC/USDT", {"sample": 1})
    await memory.set("market:context:ETH/USDT", {"sample": 2})
    await memory.set("other:key", {"value": 3})

    keys = await memory.get_keys_by_pattern("market:context:*")
    assert sorted(keys) == ["market:context:BTC/USDT", "market:context:ETH/USDT"]
