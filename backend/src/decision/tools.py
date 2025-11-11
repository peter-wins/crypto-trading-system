"""
Decision Engine Tools.

Defines LLM-invokable tools that provide market data, technical analysis,
memory retrieval and risk calculations. A simple registry is included to
expose tool schemas to LLM clients.
"""

from __future__ import annotations

import json
from abc import abstractmethod
from dataclasses import asdict, is_dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Protocol

from pydantic import BaseModel

from src.core.exceptions import ToolExecutionError
from src.core.logger import get_logger
from src.models.market import OHLCVData, Ticker
from src.models.memory import MemoryQuery, TradingExperience


logger = get_logger(__name__)


class ITool(Protocol):
    """Protocol for LLM callable tools."""

    name: str
    description: str

    @abstractmethod
    async def execute(self, **kwargs: Any) -> Any:
        """Execute tool logic asynchronously."""

    @abstractmethod
    def to_function_schema(self) -> Dict[str, Any]:
        """Represent the tool in OpenAI function-calling schema."""


class SupportsMarketData(Protocol):
    """Typing helper for market data collectors."""

    async def get_ticker(self, symbol: str) -> Ticker: ...

    async def get_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1h",
        since: int | None = None,
        limit: int = 100,
    ) -> List[OHLCVData]: ...


class SupportsIndicators(Protocol):
    """Typing helper for indicator calculators."""

    def calculate_sma(self, prices: List[Decimal], period: int) -> List[Decimal]: ...

    def calculate_ema(self, prices: List[Decimal], period: int) -> List[Decimal]: ...

    def calculate_rsi(self, prices: List[Decimal], period: int = 14) -> List[Decimal]: ...

    def calculate_macd(
        self,
        prices: List[Decimal],
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9,
    ) -> Dict[str, List[Decimal]]: ...

    def calculate_bollinger_bands(
        self,
        prices: List[Decimal],
        period: int = 20,
        std_dev: float = 2.0,
    ) -> Dict[str, List[Decimal]]: ...


class SupportsMemoryRetrieval(Protocol):
    """Typing helper for memory retrieval implementations."""

    async def retrieve_relevant_context(
        self,
        current_situation: str,
        top_k: int = 5,
    ) -> Dict[str, Any]: ...

    async def search_similar_experiences(self, query: MemoryQuery) -> List[TradingExperience]: ...


def _serialize(value: Any) -> Any:
    """Best-effort serialization for tool outputs."""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    if isinstance(value, dict):
        return {key: _serialize(val) for key, val in value.items()}
    return value


class MarketDataQueryTool:
    """Tool for querying market data via the perception module."""

    name = "market_data_query"
    description = "查询加密货币的实时市场数据，包括ticker和K线"

    def __init__(self, market_collector: SupportsMarketData) -> None:
        self.market = market_collector

    async def execute(self, **kwargs: Any) -> Dict[str, Any]:
        symbol = kwargs.get("symbol")
        data_type = kwargs.get("data_type", "ticker")
        timeframe = kwargs.get("timeframe", "1h")
        limit = kwargs.get("limit", 100)

        if not symbol:
            raise ToolExecutionError("symbol is required for market_data_query")

        try:
            if data_type == "ohlcv":
                candles = await self.market.get_ohlcv(symbol, timeframe=timeframe, limit=limit)
                return {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "data": [
                        {
                            "timestamp": candle.timestamp,
                            "open": float(candle.open),
                            "high": float(candle.high),
                            "low": float(candle.low),
                            "close": float(candle.close),
                            "volume": float(candle.volume),
                        }
                        for candle in candles
                    ],
                }

            ticker = await self.market.get_ticker(symbol)
            return {
                "symbol": ticker.symbol,
                "price": float(ticker.last),
                "bid": float(ticker.bid),
                "ask": float(ticker.ask),
                "high_24h": float(ticker.high),
                "low_24h": float(ticker.low),
                "volume_24h": float(ticker.volume),
                "quote_volume_24h": float(ticker.quote_volume),
                "change_24h": float(ticker.change_24h),
                "timestamp": ticker.timestamp,
            }
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Market data query failed: %s", exc, exc_info=True)
            raise ToolExecutionError(
                message="Failed to fetch market data",
                details={"symbol": symbol, "data_type": data_type},
                original_exception=exc,
            ) from exc

    def to_function_schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "symbol": {
                            "type": "string",
                            "description": "交易对，例如 BTC/USDT",
                        },
                        "data_type": {
                            "type": "string",
                            "enum": ["ticker", "ohlcv"],
                            "description": "查询数据类型",
                            "default": "ticker",
                        },
                        "timeframe": {
                            "type": "string",
                            "description": "K线时间周期，例如 1h、4h、1d",
                            "default": "1h",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "K线数量限制",
                            "default": 100,
                        },
                    },
                    "required": ["symbol"],
                },
            },
        }


class TechnicalAnalysisTool:
    """Tool for computing technical indicators."""

    name = "technical_analysis"
    description = "计算RSI、MACD、均线等技术指标"

    def __init__(
        self,
        market_collector: SupportsMarketData,
        indicator_calculator: SupportsIndicators,
    ) -> None:
        self.market = market_collector
        self.indicators = indicator_calculator

    async def execute(self, **kwargs: Any) -> Dict[str, Any]:
        symbol = kwargs.get("symbol")
        requested_indicators: Iterable[str] = kwargs.get("indicators", [])

        if not symbol:
            raise ToolExecutionError("symbol is required for technical_analysis")

        indicators = list(requested_indicators)
        if not indicators:
            indicators = ["rsi", "macd", "sma"]

        try:
            candles = await self.market.get_ohlcv(symbol, timeframe="1h", limit=200)
            closes = [candle.close for candle in candles]
            highs = [candle.high for candle in candles]
            lows = [candle.low for candle in candles]

            result: Dict[str, Any] = {"symbol": symbol, "indicators": {}}

            for indicator in indicators:
                indicator_lower = indicator.lower()

                if indicator_lower == "rsi":
                    rsi_values = self.indicators.calculate_rsi(closes)
                    if rsi_values:
                        result["indicators"]["rsi"] = {
                            "current": float(rsi_values[-1]),
                            "signal": _interpret_rsi(rsi_values[-1]),
                        }

                elif indicator_lower == "macd":
                    macd_data = self.indicators.calculate_macd(closes)
                    result["indicators"]["macd"] = {
                        "macd": float(macd_data["macd"][-1]),
                        "signal": float(macd_data["signal"][-1]),
                        "histogram": float(macd_data["histogram"][-1]),
                        "interpretation": _interpret_macd(macd_data),
                    }

                elif indicator_lower in {"sma", "ema"}:
                    period_fast = kwargs.get("fast_period", 20)
                    period_slow = kwargs.get("slow_period", 50)
                    if indicator_lower == "sma":
                        fast = self.indicators.calculate_sma(closes, period_fast)
                        slow = self.indicators.calculate_sma(closes, period_slow)
                    else:
                        fast = self.indicators.calculate_ema(closes, period_fast)
                        slow = self.indicators.calculate_ema(closes, period_slow)

                    result["indicators"][indicator_lower] = {
                        "fast": float(fast[-1]),
                        "slow": float(slow[-1]),
                        "trend": _interpret_moving_average(closes[-1], fast[-1], slow[-1]),
                    }

                elif indicator_lower in {"bollinger", "bbands"}:
                    bb = self.indicators.calculate_bollinger_bands(closes)
                    result["indicators"]["bollinger"] = {
                        "upper": float(bb["upper"][-1]),
                        "middle": float(bb["middle"][-1]),
                        "lower": float(bb["lower"][-1]),
                    }

            return result
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Technical analysis failed: %s", exc, exc_info=True)
            raise ToolExecutionError(
                message="Failed to compute technical indicators",
                details={"symbol": symbol, "indicators": indicators},
                original_exception=exc,
            ) from exc

    def to_function_schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string", "description": "交易对，例如 BTC/USDT"},
                        "indicators": {
                            "type": "array",
                            "description": "要计算的指标列表",
                            "items": {
                                "type": "string",
                                "enum": ["rsi", "macd", "sma", "ema", "bollinger"],
                            },
                            "default": ["rsi", "macd", "sma"],
                        },
                        "fast_period": {
                            "type": "integer",
                            "description": "快速均线周期（适用于SMA/EMA）",
                            "default": 20,
                        },
                        "slow_period": {
                            "type": "integer",
                            "description": "慢速均线周期（适用于SMA/EMA）",
                            "default": 50,
                        },
                    },
                    "required": ["symbol"],
                },
            },
        }


class MemorySearchTool:
    """Tool that queries historical experiences via memory retrieval system."""

    name = "memory_search"
    description = "搜索历史决策经验，辅助当前分析"

    def __init__(self, memory: SupportsMemoryRetrieval) -> None:
        self.memory = memory

    async def execute(self, **kwargs: Any) -> Dict[str, Any]:
        query_text = kwargs.get("query")
        outcome_filter = kwargs.get("outcome_filter")
        top_k = int(kwargs.get("top_k", 3))

        if not query_text:
            raise ToolExecutionError("query is required for memory_search")

        try:
            if hasattr(self.memory, "search_similar_experiences"):
                memory_query = MemoryQuery(
                    query_text=query_text,
                    top_k=top_k,
                    filters={"outcome": outcome_filter} if outcome_filter else {},
                )
                experiences = await self.memory.search_similar_experiences(memory_query)
                serialized = [_serialize(exp) for exp in experiences]
            else:
                context = await self.memory.retrieve_relevant_context(query_text, top_k=top_k)
                experiences = context.get("similar_experiences", [])
                serialized = [_serialize(exp) for exp in experiences]

            return {
                "query": query_text,
                "results": serialized,
            }
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Memory search failed: %s", exc, exc_info=True)
            raise ToolExecutionError(
                message="Failed to search decision memory",
                details={"query": query_text},
                original_exception=exc,
            ) from exc

    def to_function_schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "描述当前市场情形"},
                        "outcome_filter": {
                            "type": "string",
                            "enum": ["success", "failure"],
                            "description": "仅返回指定结果的经验",
                        },
                        "top_k": {
                            "type": "integer",
                            "description": "返回的经验数量",
                            "default": 3,
                        },
                    },
                    "required": ["query"],
                },
            },
        }


class RiskCalculatorTool:
    """Tool for computing simple risk metrics such as position sizing."""

    name = "risk_calculator"
    description = "根据入场价、止损和风险金额计算仓位大小及止盈"

    async def execute(self, **kwargs: Any) -> Dict[str, Any]:
        try:
            entry_price = Decimal(str(kwargs["entry_price"]))
            stop_loss_pct = Decimal(str(kwargs["stop_loss_pct"]))
            risk_amount = Decimal(str(kwargs["risk_amount"]))
        except KeyError as exc:
            raise ToolExecutionError(f"missing parameter: {exc.args[0]}") from exc
        except (InvalidOperation, ValueError) as exc:
            raise ToolExecutionError("invalid numeric parameter") from exc

        if entry_price <= 0 or stop_loss_pct <= 0 or risk_amount <= 0:
            raise ToolExecutionError("entry_price, stop_loss_pct and risk_amount must be positive")

        stop_loss_price = entry_price * (Decimal("1") - stop_loss_pct / Decimal("100"))
        risk_per_unit = entry_price - stop_loss_price
        if risk_per_unit <= 0:
            raise ToolExecutionError("stop loss produces non-positive risk per unit")

        position_size = risk_amount / risk_per_unit
        take_profit_price = entry_price + risk_per_unit * Decimal("2")  # 1:2 RR by default

        return {
            "entry_price": float(entry_price),
            "stop_loss_price": float(stop_loss_price.quantize(Decimal("0.01"))),
            "take_profit_price": float(take_profit_price.quantize(Decimal("0.01"))),
            "position_size": float(position_size.quantize(Decimal("0.0001"))),
            "risk_amount": float(risk_amount),
            "potential_profit": float((risk_amount * 2).quantize(Decimal("0.01"))),
            "risk_reward_ratio": "1:2",
        }

    def to_function_schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "entry_price": {"type": "number", "description": "计划入场价格"},
                        "stop_loss_pct": {"type": "number", "description": "止损百分比，例如 5 表示5%"},
                        "risk_amount": {"type": "number", "description": "愿意承担的风险金额（USD）"},
                    },
                    "required": ["entry_price", "stop_loss_pct", "risk_amount"],
                },
            },
        }


class ToolRegistry:
    """Registry for exposing tools to LLM clients."""

    def __init__(self) -> None:
        self._tools: Dict[str, ITool] = {}

    def register(self, tool: ITool) -> None:
        """Register a tool instance."""
        self._tools[tool.name] = tool
        logger.info("Registered decision tool: %s", tool.name)

    def get_tool(self, name: str) -> ITool | None:
        """Fetch a tool by name."""
        return self._tools.get(name)

    def get_all_schemas(self) -> List[Dict[str, Any]]:
        """Return OpenAI schema for all registered tools."""
        return [tool.to_function_schema() for tool in self._tools.values()]

    async def execute_tool(self, name: str, **kwargs: Any) -> Any:
        """Execute registered tool and serialize output for LLM consumption."""
        tool = self.get_tool(name)
        if not tool:
            raise ToolExecutionError(f"Tool not found: {name}")

        try:
            result = await tool.execute(**kwargs)
            return _serialize(result)
        except ToolExecutionError:
            raise
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Tool execution failed: %s", exc, exc_info=True)
            raise ToolExecutionError(
                message="Tool execution failed",
                details={"tool": name},
                original_exception=exc,
            ) from exc


def _interpret_rsi(value: Decimal) -> str:
    rsi = float(value)
    if rsi >= 70:
        return "overbought"
    if rsi <= 30:
        return "oversold"
    return "neutral"


def _interpret_macd(macd_data: Dict[str, List[Decimal]]) -> str:
    histogram = float(macd_data["histogram"][-1])
    if histogram > 0:
        return "bullish"
    if histogram < 0:
        return "bearish"
    return "neutral"


def _interpret_moving_average(price: Decimal, fast: Decimal, slow: Decimal) -> str:
    price_f = float(price)
    fast_f = float(fast)
    slow_f = float(slow)

    if price_f > fast_f > slow_f:
        return "strong_uptrend"
    if price_f < fast_f < slow_f:
        return "strong_downtrend"
    return "range"
