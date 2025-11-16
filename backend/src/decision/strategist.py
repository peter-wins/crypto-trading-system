"""
Strategic Decision Maker powered by LLM.

Implements the strategic layer that analyses market regimes, crafts portfolio
strategies and updates risk parameters.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Protocol

from src.core.exceptions import DecisionError, ToolExecutionError
from src.core.logger import get_logger
from src.services.llm import LLMResponse, Message, ToolCall
from src.decision.prompts import PromptTemplates
from src.decision.tools import SupportsMemoryRetrieval, ToolRegistry
from src.models.performance import PerformanceMetrics
from src.models.portfolio import Portfolio
from src.models.decision import StrategyConfig
from src.models.environment import MarketEnvironment
from src.models.regime import MarketRegime, MarketBias, MarketStructure, RiskLevel, TimeHorizon
from src.services.market_data import MarketDataCollector
from src.perception.indicators import PandasIndicatorCalculator


logger = get_logger(__name__)


class ILLMClient(Protocol):
    """Protocol for LLM clients usable by the strategist."""

    async def chat(
        self,
        messages: List[Message],
        *,
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.7,
        max_tokens: int = 4000,
    ) -> LLMResponse: ...


def _try_parse_json(content: str | None) -> Dict[str, Any]:
    if not content:
        return {}

    # 尝试直接解析
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # 尝试提取 JSON 代码块 (```json ... ```)
    import re
    json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', content, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass

    # 尝试查找 { ... } 对象
    brace_match = re.search(r'\{.*\}', content, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    return {}


def _to_decimal(value: Any, default: Decimal) -> Decimal:
    try:
        return Decimal(str(value))
    except (TypeError, ValueError, ArithmeticError):
        return default


class LLMStrategist:
    """Strategic layer orchestrating portfolio level decisions."""

    def __init__(
        self,
        llm_client: ILLMClient,
        memory_retrieval: Optional[SupportsMemoryRetrieval],
        tool_registry: Optional[ToolRegistry],
        *,
        symbols: Optional[List[str]] = None,
        max_tool_iterations: int = 6,  # 增加到6次，允许更充分的分析
        market_collector: Optional[MarketDataCollector] = None,
        indicator_calculator: Optional[PandasIndicatorCalculator] = None,
    ) -> None:
        self.llm = llm_client
        self.memory = memory_retrieval
        self.tools = tool_registry
        self.symbols = symbols or []
        self.max_tool_iterations = max_tool_iterations
        self.market_collector = market_collector
        self.indicator_calculator = indicator_calculator
        self._btc_symbol = self._detect_symbol("BTC")

    def _detect_symbol(self, base: str) -> Optional[str]:
        """根据配置匹配指定基础币种"""
        base = base.upper()
        for symbol in self.symbols:
            if symbol.upper().startswith(f"{base}/"):
                return symbol
        if any(":USDT" in symbol for symbol in self.symbols):
            return f"{base}/USDT:USDT"
        if base in ("BTC", "ETH"):
            return f"{base}/USDT"
        return None

    @staticmethod
    def _safe_float(value: Optional[Decimal]) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _infer_trend_label(self, price: Decimal, fast: Decimal, slow: Decimal) -> str:
        try:
            if price > fast > slow:
                return "上升"
            if price < fast < slow:
                return "下降"
            return "震荡"
        except Exception:  # pylint: disable=broad-except
            return "不确定"

    @staticmethod
    def _describe_volatility(ratio: float) -> str:
        if ratio >= 0.02:
            return "极高"
        if ratio >= 0.01:
            return "偏高"
        if ratio >= 0.005:
            return "中性"
        return "低"

    async def _build_symbol_market_section(self, symbol: Optional[str], label: str) -> str:
        """生成多周期行情摘要"""
        if not symbol or not self.market_collector or not self.indicator_calculator:
            return f"{label} 行情: 当前未启用实时采集或数据不可用。"

        tf_config = [("1h", "短期(1h)"), ("4h", "中期(4h)"), ("1d", "长周期(1d)")]
        lines: List[str] = [f"## {label} 多周期行情"]

        for timeframe, label_text in tf_config:
            try:
                klines = await self.market_collector.get_cached_klines(
                    symbol, timeframe=timeframe, limit=120
                )
                if not klines:
                    await self.market_collector.get_cached_klines(
                        symbol, timeframe=timeframe, limit=120, force_refresh=True
                    )
                    klines = await self.market_collector.get_cached_klines(
                        symbol, timeframe=timeframe, limit=120
                    )
            except Exception as exc:  # pylint: disable=broad-except
                logger.debug("获取 %s %s K线失败: %s", symbol, timeframe, exc)
                continue

            if not klines or len(klines) < 50:
                continue

            closes = [candle.close for candle in klines]
            highs = [candle.high for candle in klines]
            lows = [candle.low for candle in klines]
            price = closes[-1]
            prev_close = closes[-2] if len(closes) > 1 else price

            rsi_value = self.indicator_calculator.calculate_rsi(closes, 14)[-1]
            ma20 = self.indicator_calculator.calculate_sma(closes, 20)[-1]
            ma50 = self.indicator_calculator.calculate_sma(closes, 50)[-1]
            atr_value = self.indicator_calculator.calculate_atr(highs, lows, closes, 14)[-1]
            adx_data = self.indicator_calculator.calculate_adx(highs, lows, closes, 14)
            adx_value = adx_data["adx"][-1]

            trend = self._infer_trend_label(price, ma20, ma50)
            change_pct = (
                ((price - prev_close) / prev_close * Decimal("100"))
                if prev_close and prev_close != 0
                else Decimal("0")
            )
            vol_ratio = float(atr_value / price) if price and price != 0 else 0.0
            volatility = self._describe_volatility(vol_ratio)

            lines.append(
                f"- {label_text}: 收盘 {self._safe_float(price):,.2f}，"
                f"涨跌 {self._safe_float(change_pct):+.2f}%%，RSI={self._safe_float(rsi_value):.1f}，"
                f"MA20={self._safe_float(ma20):.0f}，MA50={self._safe_float(ma50):.0f}，"
                f"趋势={trend}，波动={volatility} (ATR={self._safe_float(atr_value):.2f}，ADX={self._safe_float(adx_value):.1f})"
            )

        if len(lines) == 1:
            return "BTC行情: K线数据不足，改用宏观判断。"
        return "\n".join(lines)

    async def analyze_market_regime(self, symbol: str) -> Dict[str, Any]:
        """Analyse market environment and return regime classification."""
        messages = [
            Message(role="system", content=PromptTemplates.strategist_system_prompt()),
            Message(
                role="user",
                content=(
                    f"请分析 {symbol} 的当前市场状态。需要步骤：\n"
                    "1. 使用 market_data_query 获取最新价格数据\n"
                    "2. 使用 technical_analysis 获取主要技术指标\n"
                    "3. 综合判断当前偏向（bullish/bearish/neutral）与市场结构（trending/ranging/extreme）\n"
                    "4. 输出 JSON: "
                    '{"bias": "...", "market_structure": "...", "confidence": 0-1, "key_factors": [...], "reasoning": "..."}'
                ),
            ),
        ]

        response = await self._chat_with_tools(messages)
        data = _try_parse_json(response.content)

        bias = data.get("bias", "unknown")
        confidence = float(data.get("confidence", 0.5))
        reasoning = data.get("reasoning") or response.content or ""
        key_factors = data.get("key_factors") or []

        result = {
            "bias": bias,
            "confidence": confidence,
            "reasoning": reasoning,
            "key_factors": key_factors,
            "market_structure": data.get("market_structure", "unknown"),
        }

        logger.info("Market regime analysis completed: %s", result)
        return result

    async def analyze_market_with_environment(
        self,
        environment: MarketEnvironment,
        crypto_overview: Optional[Dict[str, Any]] = None,
    ) -> MarketRegime:
        """
        基于市场环境数据进行宏观战略分析

        这是新架构的核心方法,每小时调用一次,输出 MarketRegime 给战术层使用

        Args:
            environment: 感知层提供的完整市场环境数据
            crypto_overview: 加密市场概览数据 (可选)

        Returns:
            MarketRegime: 市场状态判断,包含币种筛选、风险评估、策略建议等
        """
        logger.info("开始战略层分析 (基于市场环境)...")

        # 构建环境摘要给 LLM
        env_summary = self._build_environment_summary(environment)

        # 构建加密市场概览
        crypto_summary = "暂无"
        if crypto_overview:
            lines = ["- 总市值: ${:,.0f}".format(float(crypto_overview.get("total_market_cap", 0)))]
            if crypto_overview.get("market_cap_change_24h") is not None:
                lines.append(f"- 市值24h变化: {crypto_overview['market_cap_change_24h']:+.2f}%")
            if crypto_overview.get("btc_dominance") is not None:
                lines.append(f"- BTC市值占比: {crypto_overview['btc_dominance']:.1f}%")
            if crypto_overview.get("total_volume_24h") is not None:
                lines.append("- 24h成交量: ${:,.0f}".format(float(crypto_overview["total_volume_24h"])))
            crypto_summary = "\n".join(lines)

        # 使用模板配置
        from src.decision.prompt_templates import PromptTemplateConfig, PromptStyle
        from src.core.config import get_config

        config = get_config()
        try:
            style = PromptStyle(config.prompt_style)
        except ValueError:
            style = PromptStyle.BALANCED

        # 模板已经使用 %s 预填充了配置，直接替换数据占位符
        template = PromptTemplateConfig.get_strategist_user_template(style)

        # 格式化可用币种列表
        available_symbols = self.symbols if self.symbols else []
        # 移除合约后缀，只显示基础交易对
        clean_symbols = [s.replace(':USDT', '') for s in available_symbols]
        symbols_str = f"可选币种: {', '.join(clean_symbols)}" if clean_symbols else "可选币种: 无"
        btc_market_summary = await self._build_symbol_market_section(self._btc_symbol, "BTC")
        eth_symbol = self._detect_symbol("ETH")
        eth_market_summary = ""
        if eth_symbol:
            eth_market_summary = await self._build_symbol_market_section(eth_symbol, "ETH")

        prompt = (
            template.replace("{env_summary}", env_summary)
            .replace("{btc_market}", btc_market_summary)
            .replace("{eth_market}", eth_market_summary or "暂无ETH数据")
            .replace("{crypto_summary}", crypto_summary if crypto_summary else "暂无")
            .replace("{available_symbols}", symbols_str)
        )

        # 获取战略层决策间隔（转换为小时）
        strategist_interval_hours = config.strategist_interval / 3600

        logger.debug("=" * 60)
        logger.debug("发送给战略层 LLM 的提示词:")
        logger.debug("-" * 60)
        logger.debug("System Prompt:")
        logger.debug(PromptTemplates.strategist_system_prompt(strategist_interval_hours))
        logger.debug("-" * 60)
        logger.debug("User Prompt:")
        logger.debug(prompt)
        logger.debug("=" * 60)

        messages = [
            Message(role="system", content=PromptTemplates.strategist_system_prompt(strategist_interval_hours)),
            Message(role="user", content=prompt),
        ]

        # 不使用工具，因为所有数据已经通过感知层采集并包含在提示词中
        response = await self.llm.chat(messages, tools=None)

        logger.info("=" * 60)
        logger.info("战略层 LLM 响应:")
        logger.info("-" * 60)
        logger.info(response.content or "(empty)")
        logger.info("=" * 60)

        data = _try_parse_json(response.content)

        if not data:
            logger.error(f"LLM响应内容无法解析为JSON: {response.content[:500] if response.content else 'None'}")
            raise DecisionError("LLM 未返回有效的市场状态判断,请检查响应格式")

        # 解析 bias
        bias_str = str(data.get("bias", "neutral")).lower().strip()
        try:
            bias = MarketBias(bias_str)
        except ValueError:
            logger.warning(f"未知的 bias 类型: {bias_str}, 默认为 neutral")
            bias = MarketBias.NEUTRAL

        # 解析 market_structure
        structure_str = str(data.get("market_structure", "ranging")).lower().strip()
        try:
            market_structure = MarketStructure(structure_str)
        except ValueError:
            logger.warning(f"未知的 market_structure: {structure_str}, 默认为 ranging")
            market_structure = MarketStructure.RANGING

        # 解析 risk_level
        risk_str = data.get("risk_level", "medium")
        try:
            risk_level = RiskLevel(risk_str)
        except ValueError:
            logger.warning(f"未知的 risk_level: {risk_str}, 默认为 medium")
            risk_level = RiskLevel.MEDIUM

        # 解析 time_horizon (支持复合值映射)
        horizon_str = data.get("time_horizon", "medium").lower().strip()

        # 复合值映射表
        horizon_mapping = {
            "short-to-medium": TimeHorizon.MEDIUM,
            "medium-to-long": TimeHorizon.LONG,
            "short-medium": TimeHorizon.MEDIUM,
            "medium-long": TimeHorizon.LONG,
        }

        # 先尝试直接匹配
        try:
            time_horizon = TimeHorizon(horizon_str)
        except ValueError:
            # 尝试从映射表查找
            time_horizon = horizon_mapping.get(horizon_str)
            if time_horizon:
                logger.info(f"将复合时间跨度 '{horizon_str}' 映射为 '{time_horizon.value}'")
            else:
                logger.warning(f"未知的 time_horizon: {horizon_str}, 默认为 medium")
                time_horizon = TimeHorizon.MEDIUM

        # 生成时间戳
        now = datetime.now(timezone.utc)
        timestamp = int(now.timestamp() * 1000)
        valid_until = timestamp + 3600 * 1000  # 1小时后过期

        # 构建 MarketRegime
        market_regime = MarketRegime(
            bias=bias,
            market_structure=market_structure,
            confidence=float(data.get("confidence", 0.5)),
            risk_level=risk_level,
            market_narrative=data.get("market_narrative", ""),
            key_drivers=data.get("key_drivers", []),
            volatility_range=data.get("volatility_range"),
            time_horizon=time_horizon,
            cash_ratio=float(data.get("cash_ratio", 0.3)),
            max_exposure=(
                float(data.get("max_exposure"))
                if data.get("max_exposure") is not None
                else None
            ),
            trading_mode=data.get("trading_mode", "normal"),
            position_sizing_multiplier=float(data.get("position_sizing_multiplier", 1.0)),
            timestamp=timestamp,
            dt=now,
            valid_until=valid_until,
            reasoning=data.get("reasoning", response.content or ""),
        )

        return market_regime

    def _build_environment_summary(self, environment: MarketEnvironment) -> str:
        """构建环境数据的文本摘要供 LLM 分析"""
        parts = []
        structured: Dict[str, Any] = {}

        # 宏观数据
        if environment.macro:
            macro = environment.macro
            parts.append("## 宏观经济")
            if macro.fed_rate is not None:
                parts.append(f"- 联邦基金利率: {macro.fed_rate}%")
            if macro.fed_rate_trend:
                parts.append(f"- 利率趋势: {macro.fed_rate_trend}")
            if macro.cpi is not None:
                parts.append(f"- CPI 通胀率: {macro.cpi}%")
            if macro.unemployment is not None:
                parts.append(f"- 失业率: {macro.unemployment}%")
            if macro.dxy is not None:
                parts.append(f"- 美元指数: {macro.dxy}")
            if macro.dxy_change_24h is not None:
                parts.append(f"- 美元指数24h变化: {macro.dxy_change_24h:+.2f}%")
            if macro.gold_price is not None:
                parts.append(f"- 黄金价格: ${macro.gold_price}/oz")
            if macro.oil_price is not None:
                parts.append(f"- 原油价格: ${macro.oil_price}/barrel")
            structured["macro"] = {
                "fed_rate": macro.fed_rate,
                "fed_rate_trend": macro.fed_rate_trend,
                "cpi": macro.cpi,
                "unemployment": macro.unemployment,
                "dxy": macro.dxy,
                "dxy_change_24h": macro.dxy_change_24h,
                "gold_price": macro.gold_price,
                "oil_price": macro.oil_price,
            }

        # 美股数据
        if environment.stock_market:
            stock = environment.stock_market
            parts.append("\n## 美股市场")
            if stock.sp500 is not None:
                parts.append(f"- 标普500: {stock.sp500}")
            if stock.sp500_change_24h is not None:
                parts.append(f"- 标普500 24h变化: {stock.sp500_change_24h:+.2f}%")
            if stock.nasdaq is not None:
                parts.append(f"- 纳斯达克: {stock.nasdaq}")
            if stock.nasdaq_change_24h is not None:
                parts.append(f"- 纳斯达克 24h变化: {stock.nasdaq_change_24h:+.2f}%")
            if stock.coin_stock is not None:
                parts.append(f"- COIN股价: ${stock.coin_stock}")
            if stock.coin_change_24h is not None:
                parts.append(f"- COIN 24h变化: {stock.coin_change_24h:+.2f}%")
            if stock.mstr_stock is not None:
                parts.append(f"- MSTR股价: ${stock.mstr_stock}")
            if stock.mstr_change_24h is not None:
                parts.append(f"- MSTR 24h变化: {stock.mstr_change_24h:+.2f}%")
            structured["equities"] = {
                "sp500": stock.sp500,
                "sp500_change_24h": stock.sp500_change_24h,
                "nasdaq": stock.nasdaq,
                "nasdaq_change_24h": stock.nasdaq_change_24h,
                "coin": stock.coin_stock,
                "coin_change_24h": stock.coin_change_24h,
                "mstr": stock.mstr_stock,
                "mstr_change_24h": stock.mstr_change_24h,
            }

        # 情绪数据
        if environment.sentiment:
            sentiment = environment.sentiment
            parts.append("\n## 市场情绪")
            if sentiment.fear_greed_index is not None:
                parts.append(
                    f"- 恐慌贪婪指数: {sentiment.fear_greed_index} "
                    f"({sentiment.fear_greed_label or 'unknown'})"
                )
                parts.append(f"- 综合情绪: {sentiment.get_overall_sentiment()}")
            if sentiment.btc_funding_rate is not None:
                parts.append(f"- BTC资金费率: {sentiment.btc_funding_rate:.4f}%")
            if sentiment.eth_funding_rate is not None:
                parts.append(f"- ETH资金费率: {sentiment.eth_funding_rate:.4f}%")
            if sentiment.btc_long_short_ratio is not None:
                parts.append(f"- BTC多空比: {sentiment.btc_long_short_ratio:.2f}")
            if sentiment.eth_long_short_ratio is not None:
                parts.append(f"- ETH多空比: {sentiment.eth_long_short_ratio:.2f}")
            fg = sentiment.get_overall_sentiment()
            funding_values = [
                v for v in [sentiment.btc_funding_rate, sentiment.eth_funding_rate]
                if v is not None
            ]
            structured["sentiment"] = {
                "fear_greed_index": sentiment.fear_greed_index,
                "fear_greed_label": sentiment.fear_greed_label,
                "overall": fg,
                "btc_funding_rate": sentiment.btc_funding_rate,
                "eth_funding_rate": sentiment.eth_funding_rate,
                "funding_avg": (
                    sum(funding_values) / len(funding_values) if funding_values else None
                ),
                "btc_long_short": sentiment.btc_long_short_ratio,
                "eth_long_short": sentiment.eth_long_short_ratio,
            }

        # 新闻事件
        if environment.recent_news:
            parts.append(f"\n## 重大新闻 (最近24小时, 共{len(environment.recent_news)}条)")
            for news in environment.recent_news[:5]:  # 最多显示5条
                parts.append(
                    f"- [{news.impact_level}] {news.title} "
                    f"(情绪: {news.sentiment}, 来源: {news.source})"
                )

        parts.append(f"\n数据完整度: {environment.data_completeness:.0%}")

        def _convert(obj: Any):
            if isinstance(obj, dict):
                return {k: _convert(v) for k, v in obj.items() if v is not None}
            if isinstance(obj, list):
                return [_convert(v) for v in obj]
            if isinstance(obj, Decimal):
                return float(obj)
            return obj

        structured_filtered = _convert(structured)
        if structured_filtered:
            parts.append("\n### 结构化指标")
            parts.append(
                "```json\n"
                + json.dumps(structured_filtered, ensure_ascii=False, indent=2)
                + "\n```"
            )

        return "\n".join(parts)

    async def make_strategic_decision(self, portfolio: Portfolio) -> StrategyConfig:
        """Create or update strategy configuration based on current portfolio."""
        context = await self._build_context(portfolio)
        messages = [
            Message(role="system", content=PromptTemplates.strategist_system_prompt()),
            Message(role="user", content=PromptTemplates.build_strategist_prompt(context)),
        ]

        response = await self._chat_with_tools(messages)
        data = _try_parse_json(response.content)

        strategy_payload = data.get("strategy", {})
        risk_payload = data.get("risk_parameters", {})

        now = datetime.now(timezone.utc)
        trading_pairs = strategy_payload.get("trading_pairs") or [
            pos["symbol"] for pos in context["portfolio"]["positions"]
        ] or ["BTC/USDT"]

        strategy = StrategyConfig(
            name=strategy_payload.get("name", "adaptive_strategy"),
            version=str(strategy_payload.get("version", "1.0.0")),
            description=strategy_payload.get("description", response.content or "AI generated strategy"),
            max_position_size=_to_decimal(risk_payload.get("max_position_size", 0.2), Decimal("0.2")),
            max_single_trade=_to_decimal(risk_payload.get("max_single_trade", 1000), Decimal("1000")),
            max_open_positions=int(strategy_payload.get("max_open_positions", 3)),
            max_daily_loss=_to_decimal(risk_payload.get("max_daily_loss", 0.05), Decimal("0.05")),
            max_drawdown=_to_decimal(risk_payload.get("max_drawdown", 0.15), Decimal("0.15")),
            stop_loss_percentage=_to_decimal(risk_payload.get("stop_loss_percentage", 5), Decimal("5")),
            take_profit_percentage=_to_decimal(risk_payload.get("take_profit_percentage", 10), Decimal("10")),
            trading_pairs=trading_pairs,
            timeframes=strategy_payload.get("timeframes", ["1h", "4h"]),
            updated_at=now,
            reason_for_update=data.get("reasoning", response.content or "Periodic strategic review"),
        )

        logger.info("Generated strategy config %s (%s)", strategy.name, strategy.version)
        return strategy

    async def update_risk_parameters(self, performance: PerformanceMetrics) -> Dict[str, Decimal]:
        """Request updated risk parameters based on recent performance."""
        metrics = performance.model_dump(mode="json")

        summary = json.dumps(metrics, ensure_ascii=False, default=str)
        messages = [
            Message(role="system", content=PromptTemplates.strategist_system_prompt()),
            Message(
                role="user",
                content=(
                    "基于以下绩效指标更新风险参数，输出JSON："
                    '{"max_position_size": ..., "max_daily_loss": ..., "max_drawdown": ..., '
                    '"stop_loss_percentage": ..., "take_profit_percentage": ...}\n\n'
                    f"{summary}"
                ),
            ),
        ]

        response = await self._chat_with_tools(messages)
        data = _try_parse_json(response.content)

        if not data:
            logger.warning("LLM did not return structured risk parameters, using defaults.")
            return {
                "max_position_size": Decimal("0.2"),
                "max_daily_loss": Decimal("0.05"),
                "max_drawdown": Decimal("0.15"),
                "stop_loss_percentage": Decimal("5"),
                "take_profit_percentage": Decimal("10"),
            }

        return {key: _to_decimal(value, Decimal("0")) for key, value in data.items()}

    async def _build_context(self, portfolio: Portfolio) -> Dict[str, Any]:
        """Gather contextual information for prompt building."""
        portfolio_dict = {
            "total_value": float(portfolio.total_value),
            "cash": float(portfolio.cash),
            "positions": [
                {
                    "symbol": position.symbol,
                    "side": position.side.value,
                    "amount": float(position.amount),
                    "value": float(position.value),
                    "unrealized_pnl": float(position.unrealized_pnl),
                }
                for position in portfolio.positions
            ],
            "total_return": float(portfolio.total_return),
        }

        context: Dict[str, Any] = {
            "portfolio": portfolio_dict,
            "performance": {
                "7d_return": 0.0,
                "30d_return": 0.0,
                "sharpe_ratio": 0.0,
                "max_drawdown": 0.0,
            },
            "similar_experiences": "暂无数据",
            "symbols": self.symbols,  # 添加交易对列表
        }

        if not self.memory:
            return context

        try:
            memory_context = await self.memory.retrieve_relevant_context(
                current_situation=(
                    f"Portfolio value ${portfolio.total_value}, "
                    f"return {portfolio.total_return}%"
                ),
                top_k=3,
            )
            if memory_context:
                context["similar_experiences"] = _serialize_for_prompt(
                    memory_context.get("similar_experiences")
                )
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Failed to retrieve memory context: %s", exc)

        return context

    async def _chat_with_tools(self, messages: List[Message]) -> LLMResponse:
        """Handle multi-turn tool calling loop."""
        history = list(messages)
        tool_schemas = self.tools.get_all_schemas() if self.tools else None

        used_tools: set[str] = set()
        response: Optional[LLMResponse] = None
        for iteration in range(self.max_tool_iterations):
            response = await self.llm.chat(history, tools=tool_schemas)

            # If no tool call requested, finish.
            if not response.tool_calls:
                return response

            # Append assistant message with tool metadata.
            history.append(
                Message(
                    role="assistant",
                    content=response.content,
                    tool_calls=response.tool_calls,
                )
            )

            # Execute tool calls sequentially.
            if not self.tools:
                logger.warning("LLM 请求调用工具，但当前未注册任何工具。")
                continue

            for call in response.tool_calls:
                await self._handle_tool_call(history, call)
                used_tools.add(call.name)

            # 每次工具调用后提示，但不强制立即结束
            if iteration < self.max_tool_iterations - 2:
                # 前几轮：温和提示
                history.append(
                    Message(
                        role="system",
                        content="如果已收集足够信息，请输出最终决策JSON；否则可继续使用工具。"
                    )
                )
            else:
                # 最后1-2轮：强烈提示
                history.append(
                    Message(
                        role="system",
                        content=(
                            "⚠️ 已接近工具调用上限。请基于现有数据立即输出最终 JSON 决策，"
                            "格式：{...}，不要继续调用工具。"
                        ),
                    )
                )

        logger.info("LLM 调用工具达到 %s 次上限，已输出最终决策。", self.max_tool_iterations)
        if response is None:
            raise DecisionError("LLM 未返回有效响应。")
        return response

    async def _handle_tool_call(self, history: List[Message], tool_call: ToolCall) -> None:
        """Execute tool call and append result to conversation history."""
        if not self.tools:
            return

        try:
            result = await self.tools.execute_tool(tool_call.name, **tool_call.arguments)
        except ToolExecutionError as exc:
            logger.error("Strategist 工具执行失败: %s", exc)
            result = {"error": str(exc)}

        history.append(
            Message(
                role="tool",
                name=tool_call.name,
                tool_call_id=tool_call.id,
                content=json.dumps(result, ensure_ascii=False, default=str),
            )
        )


def _serialize_for_prompt(experiences: Any) -> str:
    """Assemble human-readable description for memory items."""
    if not experiences:
        return "暂无相关经验"

    try:
        serialized = []
        for idx, item in enumerate(experiences, start=1):
            if isinstance(item, dict):
                situation = item.get("situation", "未知情景")
                decision = item.get("decision", "无决策记录")
                outcome = item.get("outcome", "未知")
                lessons = item.get("lessons_learned", [])
            else:
                situation = getattr(item, "situation", "未知情景")
                decision = getattr(item, "decision", "无决策记录")
                outcome = getattr(item, "outcome", "未知")
                lessons = getattr(item, "lessons_learned", [])

            serialized.append(
                f"{idx}. 情景: {situation}\n   决策: {decision}\n   结果: {outcome}\n   经验: {lessons}"
            )

        return "\n".join(serialized)
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("Failed to serialize experiences: %s", exc)
        return "历史经验解析失败"
