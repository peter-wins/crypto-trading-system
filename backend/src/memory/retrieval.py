"""
RAG Memory Retrieval Module.

Combines short-term (Redis) and long-term (Qdrant) memories to provide
contextual information for downstream LLM decision agents.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Protocol

from src.core.logger import get_logger
from src.models.memory import MarketContext, MemoryQuery, TradingContext, TradingExperience
from src.models.portfolio import Portfolio


logger = get_logger(__name__)


class SupportsShortTermMemory(Protocol):
    """Protocol for short-term memory implementation."""

    async def get_market_context(self, symbol: str) -> Optional[MarketContext]: ...

    async def update_market_context(self, symbol: str, context: MarketContext) -> bool: ...

    async def get_trading_context(self) -> Optional[TradingContext]: ...

    async def update_trading_context(self, context: TradingContext) -> bool: ...


class SupportsLongTermMemory(Protocol):
    """Protocol for long-term memory implementation."""

    async def search_similar_experiences(self, query: MemoryQuery) -> List[TradingExperience]: ...


class RAGMemoryRetrieval:
    """Retrieval Augmented Generation helper for decision modules."""

    def __init__(
        self,
        short_term: SupportsShortTermMemory,
        long_term: SupportsLongTermMemory,
        *,
        default_top_k: int = 5,
    ) -> None:
        self.short_term = short_term
        self.long_term = long_term
        self.default_top_k = default_top_k
        self.logger = get_logger(self.__class__.__name__)

    async def retrieve_relevant_context(
        self,
        current_situation: str,
        top_k: int = 5,
        *,
        outcome_filter: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Retrieve blended context for a given situation.

        Returns a dictionary containing similar long-term experiences alongside
        the latest trading and market contexts stored in Redis.
        """
        experiences: List[TradingExperience] = []
        trading_context: Optional[TradingContext] = None
        market_context: Optional[MarketContext] = None

        self.logger.debug("Retrieving context for situation: %s", current_situation)

        try:
            query = MemoryQuery(
                query_text=current_situation,
                top_k=top_k or self.default_top_k,
                filters={"outcome": outcome_filter} if outcome_filter else {},
            )
            experiences = await self.long_term.search_similar_experiences(query)
        except Exception as exc:  # pylint: disable=broad-except
            self.logger.error("Failed to retrieve experiences: %s", exc)

        try:
            trading_context = await self.short_term.get_trading_context()
            if trading_context:
                market_context = trading_context.market_context
        except Exception as exc:  # pylint: disable=broad-except
            self.logger.error("Failed to load trading context: %s", exc)

        return {
            "similar_experiences": experiences,
            "current_context": trading_context,
            "market_context": market_context,
        }

    async def build_context_for_llm(
        self,
        symbol: str,
        decision_type: str,
        *,
        top_k: Optional[int] = None,
    ) -> str:
        """
        Build a formatted context string for LLM prompts.

        The prompt includes current market context, trading context, and a
        concise summary of similar historical experiences.
        """
        market_context: Optional[MarketContext] = None
        trading_context: Optional[TradingContext] = None
        experiences: List[TradingExperience] = []

        try:
            market_context = await self.short_term.get_market_context(symbol)
        except Exception as exc:  # pylint: disable=broad-except
            self.logger.error("Failed to fetch market context for %s: %s", symbol, exc)

        try:
            trading_context = await self.short_term.get_trading_context()
        except Exception as exc:  # pylint: disable=broad-except
            self.logger.error("Failed to fetch trading context: %s", exc)

        try:
            query_text = f"{decision_type} decision for {symbol}"
            query = MemoryQuery(
                query_text=query_text,
                top_k=top_k or self.default_top_k,
                filters={"outcome": "success"} if decision_type == "strategic" else {},
            )
            experiences = await self.long_term.search_similar_experiences(query)
        except Exception as exc:  # pylint: disable=broad-except
            self.logger.error("Failed to search similar experiences: %s", exc)

        prompt = self._format_context_prompt(
            symbol, decision_type, market_context, trading_context, experiences
        )

        self.logger.debug("Built context prompt for %s (%s)", symbol, decision_type)
        return prompt

    # --------------------------------------------------------------------- #
    # Formatting helpers
    # --------------------------------------------------------------------- #

    def _format_context_prompt(
        self,
        symbol: str,
        decision_type: str,
        market_context: Optional[MarketContext],
        trading_context: Optional[TradingContext],
        experiences: Iterable[TradingExperience],
    ) -> str:
        lines: List[str] = [
            f"决策类型: {decision_type}",
            f"交易对: {symbol}",
        ]

        lines.append("")
        lines.append("=== 市场上下文 ===")
        if market_context:
            lines.extend(self._format_market_context(market_context))
        else:
            lines.append("暂无市场上下文数据。")

        lines.append("")
        lines.append("=== 交易上下文 ===")
        if trading_context:
            lines.extend(self._format_trading_context(trading_context))
        else:
            lines.append("暂无交易上下文数据。")

        lines.append("")
        lines.append("=== 相似经验 ===")
        exp_lines = list(self._format_experiences(experiences))
        if exp_lines:
            lines.extend(exp_lines)
        else:
            lines.append("暂无历史经验可供参考。")

        return "\n".join(lines).strip()

    def _format_market_context(self, context: MarketContext) -> List[str]:
        prices_preview = ", ".join(_format_decimal(p) for p in context.recent_prices[:5])
        indicators = ", ".join(f"{k}: {v}" for k, v in context.indicators.items())
        trades = ", ".join(context.recent_trades) if context.recent_trades else "无"

        return [
            f"时间: {context.dt.isoformat()}",
            f"市场状态: {context.market_regime}",
            f"波动率: {_format_decimal(context.volatility)}",
            f"趋势: {context.trend}",
            f"近期价格: {prices_preview or '无'}",
            f"技术指标: {indicators or '无'}",
            f"近期交易: {trades}",
        ]

    def _format_trading_context(self, context: TradingContext) -> List[str]:
        strategy_params = ", ".join(f"{k}={v}" for k, v in context.strategy_params.items())
        risk_info = [
            f"最大仓位: {_format_percent(context.max_position_size)}",
            f"最大日亏损: {_format_percent(context.max_daily_loss)}",
            f"当日亏损: {_format_percent(context.current_daily_loss)}",
        ]
        portfolio_summary = self._summarise_portfolio(context.portfolio)

        return [
            f"时间: {context.dt.isoformat()}",
            f"当前策略: {context.current_strategy}",
            f"策略参数: {strategy_params or '无'}",
            *risk_info,
            f"投资组合: {portfolio_summary}",
        ]

    def _format_experiences(self, experiences: Iterable[TradingExperience]) -> Iterable[str]:
        for idx, exp in enumerate(experiences, start=1):
            lessons = ", ".join(exp.lessons_learned) if exp.lessons_learned else "无"
            yield (
                f"{idx}. 时间: {exp.dt.isoformat()} | 情景: {exp.situation} | "
                f"决策: {exp.decision} | 结果: {exp.outcome} | "
                f"盈亏: {_format_decimal(exp.pnl)} "
                f"({_format_percent(exp.pnl_percentage)}) | 经验: {lessons}"
            )

    def _summarise_portfolio(self, portfolio: Portfolio) -> str:
        positions = [
            f"{pos.symbol}:{_format_decimal(pos.value)}({pos.side.value})"
            for pos in portfolio.positions
        ]
        return (
            f"总价值 ${_format_decimal(portfolio.total_value)} | "
            f"现金 ${_format_decimal(portfolio.cash)} | "
            f"持仓 {', '.join(positions) if positions else '无'}"
        )


def _format_decimal(value: Decimal | float | int) -> str:
    if isinstance(value, Decimal):
        normalized = value.normalize()
        text = format(normalized, "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text or "0"
    return f"{value}"


def _format_percent(value: Decimal | float | int) -> str:
    if isinstance(value, Decimal):
        numeric = value
    else:
        numeric = Decimal(str(value))

    if Decimal("-1") <= numeric <= Decimal("1"):
        percent = numeric * Decimal("100")
    else:
        percent = numeric

    return f"{percent:.2f}%"
