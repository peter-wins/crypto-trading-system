"""
Tactical Trader powered by LLM.

Generates trading signals and position sizing guidance under strategic
constraints.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
from typing import Any, Dict, List, Optional, Protocol

from src.core.exceptions import DecisionError, ToolExecutionError
from src.core.logger import get_logger
from src.services.llm import LLMResponse, Message, ToolCall
from src.decision.prompts import PromptTemplates
from src.decision.tools import SupportsMemoryRetrieval, ToolRegistry
from src.models.decision import SignalType, StrategyConfig, TradingSignal
from src.models.portfolio import Portfolio
from src.models.regime import MarketRegime


logger = get_logger(__name__)


class ILLMClient(Protocol):
    """Protocol required from LLM client implementations."""

    async def chat(
        self,
        messages: List[Message],
        *,
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.2,
        max_tokens: int = 2000,
    ) -> LLMResponse: ...


def _to_decimal(value: Any, default: Decimal) -> Decimal:
    try:
        return Decimal(str(value))
    except (TypeError, ValueError, ArithmeticError):
        return default


def _normalize_percentage(value: Decimal) -> Decimal:
    """Ensure percentage represented as fraction (0-1)."""
    if value > 1:
        return value / Decimal("100")
    return value


def _parse_signal_type(value: str | None) -> SignalType:
    mapping = {
        "enter_long": SignalType.ENTER_LONG,
        "long": SignalType.ENTER_LONG,
        "buy": SignalType.ENTER_LONG,
        "exit_long": SignalType.EXIT_LONG,
        "take_profit_long": SignalType.EXIT_LONG,
        "enter_short": SignalType.ENTER_SHORT,
        "short": SignalType.ENTER_SHORT,
        "sell_short": SignalType.ENTER_SHORT,
        "exit_short": SignalType.EXIT_SHORT,
        "cover": SignalType.EXIT_SHORT,
        "hold": SignalType.HOLD,
        "wait": SignalType.HOLD,
    }
    return mapping.get((value or "").lower(), SignalType.HOLD)


class LLMTrader:
    """LLM-driven tactical trader implementation."""

    def __init__(
        self,
        llm_client: ILLMClient,
        tool_registry: Optional[ToolRegistry],
        memory_retrieval: Optional[SupportsMemoryRetrieval],
        *,
        max_tool_iterations: int = 6,  # 增加到6次，允许充分的技术分析
    ) -> None:
        self.llm = llm_client
        self.tools = tool_registry
        self.memory = memory_retrieval
        self.max_tool_iterations = max_tool_iterations

    async def batch_generate_signals_with_regime(
        self,
        market_regime: MarketRegime,
        symbols_snapshots: Dict[str, Dict[str, Any]],
        portfolio: Optional[Portfolio] = None,
    ) -> Dict[str, Optional[TradingSignal]]:
        """
        基于市场状态判断进行批量交易决策 (新架构)

        这是新架构的战术层核心方法,每3-5分钟调用一次

        Args:
            market_regime: 战略层提供的市场状态判断
            symbols_snapshots: {symbol: market_snapshot} 仅包含 regime 推荐的币种
            portfolio: 当前持仓信息

        Returns:
            {symbol: TradingSignal or None}
        """
        if not symbols_snapshots:
            return {}

        logger.info(
            f"战术层开始批量分析 (市场状态: {market_regime.regime.value}, "
            f"风险等级: {market_regime.risk_level.value})"
        )

        # 构建包含 regime 信息的上下文
        batch_context = await self._build_batch_context_with_regime(
            market_regime, symbols_snapshots, portfolio
        )

        # 构建提示词
        prompt = self._build_regime_aware_prompt(batch_context)

        # 获取决策间隔信息用于系统提示词
        trading_intervals = batch_context.get("trading_intervals", {})
        trader_interval_minutes = trading_intervals.get("trader_interval_seconds", 180) / 60
        strategist_interval_hours = trading_intervals.get("strategist_interval_seconds", 3600) / 3600

        logger.info("=" * 60)
        logger.info(f"战术层批量分析 {len(symbols_snapshots)} 个交易对")
        logger.info("=" * 60)
        logger.debug("发送给 LLM 的提示词:")
        logger.debug("-" * 60)
        logger.debug("System Prompt:")
        logger.debug(PromptTemplates.trader_system_prompt(trader_interval_minutes, strategist_interval_hours))
        logger.debug("-" * 60)
        logger.debug("User Prompt:")
        logger.debug(prompt)
        logger.debug("=" * 60)

        messages = [
            Message(role="system", content=PromptTemplates.trader_system_prompt(trader_interval_minutes, strategist_interval_hours)),
            Message(role="user", content=prompt),
        ]

        # 调用 LLM (不使用工具,因为数据已提供)
        response = await self.llm.chat(messages, tools=None)

        logger.info("=" * 60)
        logger.info("战术层批量分析响应:")
        logger.info("-" * 60)
        logger.info(response.content or "(empty)")
        logger.info("=" * 60)

        # 解析批量响应
        signals = self._parse_batch_signals(response, symbols_snapshots.keys())

        logger.info("批量信号生成完成: %d/%d", len(signals), len(symbols_snapshots))
        return signals

    async def batch_generate_signals(
        self,
        symbols_snapshots: Dict[str, Dict[str, Any]],
        strategy_config: StrategyConfig,
        portfolio: Optional[Portfolio] = None,
    ) -> Dict[str, Optional[TradingSignal]]:
        """
        批量分析多个交易对，一次LLM调用生成所有信号

        Args:
            symbols_snapshots: {symbol: market_snapshot}
            strategy_config: 策略配置
            portfolio: 持仓信息

        Returns:
            {symbol: TradingSignal or None}
        """
        if not symbols_snapshots:
            return {}

        # 构建批量上下文
        batch_context = await self._build_batch_context(
            symbols_snapshots, strategy_config, portfolio
        )

        # 构建批量提示词
        prompt = PromptTemplates.build_batch_trader_prompt(batch_context)

        logger.info("=" * 60)
        logger.info(f"批量分析 {len(symbols_snapshots)} 个交易对")
        logger.info("=" * 60)
        logger.info("批量分析提示词:")
        logger.info("-" * 60)
        logger.info(prompt)
        logger.info("=" * 60)

        messages = [
            Message(role="system", content=PromptTemplates.trader_system_prompt()),
            Message(role="user", content=prompt),
        ]

        # 调用LLM（不使用工具，因为数据已提供）
        response = await self.llm.chat(messages, tools=None)

        logger.info("=" * 60)
        logger.info("LLM 批量分析响应:")
        logger.info("-" * 60)
        logger.info(response.content or "(empty)")
        logger.info("=" * 60)

        # 解析批量响应
        signals = self._parse_batch_signals(response, symbols_snapshots.keys())

        logger.info("批量信号生成完成: %d/%d", len(signals), len(symbols_snapshots))
        return signals

    async def generate_trading_signal(
        self,
        symbol: str,
        strategy_config: StrategyConfig,
        portfolio: Optional[Portfolio] = None,
        market_snapshot: Optional[Dict[str, Any]] = None,
    ) -> TradingSignal:
        """Generate a trading signal respecting strategy configuration."""
        context = await self._build_context(symbol, strategy_config, portfolio, market_snapshot)
        prompt = PromptTemplates.build_trader_prompt(symbol, context)

        # 记录发送给LLM的完整提示词（用于调试）
        logger.info("=" * 60)
        logger.info(f"发送给 LLM 的提示词 ({symbol}):")
        logger.info("-" * 60)
        logger.info(prompt)
        logger.info("=" * 60)

        messages = [
            Message(role="system", content=PromptTemplates.trader_system_prompt()),
            Message(role="user", content=prompt),
        ]

        # 不使用工具，因为市场数据已经包含在提示词中
        response = await self.llm.chat(messages, tools=None)

        # 记录LLM的完整响应用于调试
        logger.info("=" * 60)
        logger.info("LLM Trader 响应内容:")
        logger.info("-" * 60)
        logger.info(response.content if response.content else "(无文本内容)")
        logger.info("=" * 60)

        payload = _try_parse_json(response.content)

        now = datetime.now(tz=timezone.utc)
        timestamp = int(now.timestamp() * 1000)

        signal_type = _parse_signal_type(payload.get("signal_type"))
        confidence = float(payload.get("confidence", 0.5))
        reasoning = payload.get("reasoning", response.content or "")
        supporting = payload.get("factors", {}).get("supporting", [])
        risks = payload.get("factors", {}).get("risks", [])

        suggested_price = payload.get("suggested_price") or payload.get("entry_price")
        stop_loss = payload.get("stop_loss")
        take_profit = payload.get("take_profit")
        suggested_amount = payload.get("suggested_amount")
        leverage = payload.get("leverage")

        signal = TradingSignal(
            timestamp=timestamp,
            dt=now,
            symbol=symbol,
            signal_type=signal_type,
            confidence=confidence,
            suggested_price=_to_decimal(suggested_price, Decimal("0")) if suggested_price else None,
            suggested_amount=_to_decimal(suggested_amount, Decimal("0")) if suggested_amount else None,
            stop_loss=_to_decimal(stop_loss, Decimal("0")) if stop_loss else None,
            take_profit=_to_decimal(take_profit, Decimal("0")) if take_profit else None,
            leverage=int(leverage) if leverage else None,
            reasoning=reasoning,
            supporting_factors=supporting or [],
            risk_factors=risks or [],
            source="trader",
        )

        logger.info(
            "生成交易信号 %s，置信度 %.2f",
            signal.signal_type.value,
            confidence,
        )
        return signal

    async def calculate_position_size(
        self,
        signal: TradingSignal,
        portfolio: Portfolio,
        risk_params: Dict[str, Decimal],
    ) -> Decimal:
        """Calculate recommended position size based on portfolio and risk constraints."""
        if not signal.suggested_price or signal.suggested_price <= 0:
            logger.warning("Signal missing suggested price, cannot size position.")
            return Decimal("0")

        total_value = portfolio.total_value
        cash_available = portfolio.cash

        max_position_fraction = _normalize_percentage(risk_params.get("max_position_size", Decimal("0.2")))
        max_position_value = total_value * max_position_fraction

        max_single_trade = risk_params.get("max_single_trade", None)
        if max_single_trade is not None:
            max_single_trade = Decimal(str(max_single_trade))

        max_daily_loss = _normalize_percentage(risk_params.get("max_daily_loss", Decimal("0.05")))
        risk_amount = total_value * max_daily_loss / Decimal("3")  # risk per trade budget
        stop_loss_pct = _normalize_percentage(risk_params.get("stop_loss_percentage", Decimal("5")))

        price = signal.suggested_price
        position_budget_candidates = [cash_available, max_position_value]
        if max_single_trade:
            position_budget_candidates.append(max_single_trade)

        position_value_budget = min(position_budget_candidates)
        if position_value_budget <= 0:
            return Decimal("0")

        if stop_loss_pct > 0:
            risk_budget_value = risk_amount / stop_loss_pct
            position_value_budget = min(position_value_budget, risk_budget_value)

        amount = (position_value_budget / price).quantize(Decimal("0.0001"), rounding=ROUND_DOWN)
        if signal.suggested_amount and signal.suggested_amount > 0:
            amount = min(amount, signal.suggested_amount)

        logger.info("Calculated position size %.4f for %s", amount, signal.symbol)
        return max(amount, Decimal("0"))

    async def _build_context(
        self,
        symbol: str,
        strategy: StrategyConfig,
        portfolio: Optional[Portfolio] = None,
        market_snapshot: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Assemble trader prompt context with portfolio information."""

        # 1. 构建持仓信息
        current_position_info = self._format_position_info(symbol, portfolio)

        # 2. 构建账户信息
        account_info = self._format_account_info(portfolio)

        # 3. 风险参数
        risk_params = {
            "max_position_size": float(strategy.max_position_size * Decimal("100")),
            "max_single_trade": float(strategy.max_single_trade),
            "stop_loss_percentage": float(strategy.stop_loss_percentage),
            "take_profit_percentage": float(strategy.take_profit_percentage),
        }

        # 4. 市场数据快照（如果提供）
        market_data_info = self._format_market_snapshot(market_snapshot) if market_snapshot else None

        context: Dict[str, Any] = {
            "strategy": strategy.description,
            "risk_params": risk_params,
            "current_position": current_position_info,
            "account_info": account_info,
            "market_data": market_data_info,
            "similar_cases": "暂无相关案例",
        }

        if self.memory:
            try:
                memory_context = await self.memory.retrieve_relevant_context(
                    current_situation=f"{symbol} trading opportunity",
                    top_k=3,
                )
                if memory_context:
                    experiences = memory_context.get("similar_experiences", [])
                    context["similar_cases"] = _format_cases(experiences)
            except Exception as exc:  # pylint: disable=broad-except
                logger.warning("获取记忆上下文失败: %s", exc)

        return context

    def _format_position_info(self, symbol: str, portfolio: Optional[Portfolio]) -> str:
        """格式化当前交易对的持仓信息"""
        if not portfolio:
            return "无组合信息"

        # 查找该交易对的持仓
        position = portfolio.get_position(symbol)
        if not position:
            return f"当前无 {symbol} 持仓"

        # 格式化持仓详情
        from src.models.trade import OrderSide

        pnl_pct = position.unrealized_pnl_percentage
        pnl_sign = "+" if position.unrealized_pnl >= 0 else ""
        side_name = "多头" if position.side == OrderSide.BUY else "空头"

        # 格式化杠杆倍数
        leverage_str = f"{position.leverage}x" if position.leverage else "未知"

        # 格式化强平价格
        liquidation_str = str(position.liquidation_price) if position.liquidation_price else "未设置"

        # 计算持仓时长
        from datetime import datetime, timezone
        import time
        holding_duration_str = "未知"
        if position.opened_at:
            try:
                # opened_at 可能是 datetime 对象或毫秒时间戳
                if isinstance(position.opened_at, datetime):
                    opened_at_dt = position.opened_at
                    if opened_at_dt.tzinfo is None:
                        opened_at_dt = opened_at_dt.replace(tzinfo=timezone.utc)
                    duration = datetime.now(timezone.utc) - opened_at_dt
                    duration_seconds = duration.total_seconds()
                else:
                    # 如果是毫秒时间戳（int）
                    current_time_ms = int(time.time() * 1000)
                    duration_ms = current_time_ms - int(position.opened_at)
                    duration_seconds = max(duration_ms / 1000.0, 0)

                duration_hours = duration_seconds / 3600
                if duration_hours < 1:
                    duration_minutes = duration_seconds / 60
                    holding_duration_str = f"{duration_minutes:.0f}分钟"
                elif duration_hours < 24:
                    holding_duration_str = f"{duration_hours:.1f}小时"
                else:
                    duration_days = duration_hours / 24
                    holding_duration_str = f"{duration_days:.1f}天"
            except Exception as e:
                # 如果计算失败，保持"未知"
                pass

        return (
            f"已持有 {symbol}:\n"
            f"  方向: {side_name} ({position.side.value})\n"
            f"  杠杆: {leverage_str}\n"
            f"  持仓时长: {holding_duration_str}\n"
            f"  数量: {position.amount}\n"
            f"  入场价: {position.entry_price}\n"
            f"  当前价: {position.current_price}\n"
            f"  强平价: {liquidation_str}\n"
            f"  持仓价值: {position.value} USDT\n"
            f"  未实现盈亏: {pnl_sign}{position.unrealized_pnl} USDT ({pnl_sign}{pnl_pct:.2f}%)\n"
            f"  止损价: {position.stop_loss or '未设置'}\n"
            f"  止盈价: {position.take_profit or '未设置'}"
        )

    def _format_market_snapshot(self, snapshot: Dict[str, Any]) -> str:
        """格式化市场数据快照"""
        if not snapshot:
            return "暂无市场数据"

        try:
            # 优先使用market_summary字段(如果存在)
            # 这是MarketAnalyzer生成的简洁摘要,更省token
            if "market_summary" in snapshot:
                return snapshot["market_summary"]

            # 回退到原始技术指标格式(向后兼容)
            lines = ["当前市场数据:"]

            # 价格信息
            if "latest_price" in snapshot:
                lines.append(f"  最新价格: {snapshot['latest_price']}")

            # 技术指标
            if "rsi" in snapshot:
                rsi = float(snapshot["rsi"])
                rsi_signal = "超卖" if rsi < 30 else "超买" if rsi > 70 else "中性"
                lines.append(f"  RSI(14): {rsi:.2f} ({rsi_signal})")

            if "macd" in snapshot and "macd_signal" in snapshot:
                macd = float(snapshot["macd"])
                signal = float(snapshot["macd_signal"])
                cross = "金叉" if macd > signal else "死叉"
                lines.append(f"  MACD: {macd:.4f}, Signal: {signal:.4f} ({cross})")

            if "sma_fast" in snapshot and "sma_slow" in snapshot:
                fast = float(snapshot["sma_fast"])
                slow = float(snapshot["sma_slow"])
                trend = "上升趋势" if fast > slow else "下降趋势"
                lines.append(f"  均线: 快线={fast:.2f}, 慢线={slow:.2f} ({trend})")

            if "bb_upper" in snapshot and "bb_lower" in snapshot:
                upper = float(snapshot["bb_upper"])
                lower = float(snapshot["bb_lower"])
                current = float(snapshot.get("latest_price", 0))
                if current > upper:
                    bb_pos = "突破上轨"
                elif current < lower:
                    bb_pos = "跌破下轨"
                else:
                    bb_pos = "在通道内"
                lines.append(f"  布林带: 上轨={upper:.2f}, 下轨={lower:.2f} ({bb_pos})")

            # ATR - 波动率指标(用于动态止损)
            if "atr" in snapshot:
                atr = float(snapshot["atr"])
                lines.append(f"  ATR(14): {atr:.2f} (波动率)")

            # ADX - 趋势强度指标
            if "adx" in snapshot:
                adx = float(snapshot["adx"])
                if adx < 20:
                    trend_strength = "无趋势"
                elif adx < 40:
                    trend_strength = "弱趋势"
                elif adx < 60:
                    trend_strength = "强趋势"
                else:
                    trend_strength = "极强趋势"

                # 判断趋势方向
                plus_di = float(snapshot.get("plus_di", 0))
                minus_di = float(snapshot.get("minus_di", 0))
                direction = "上升" if plus_di > minus_di else "下降"
                lines.append(f"  ADX(14): {adx:.2f} ({trend_strength}, {direction})")

            return "\n".join(lines)

        except Exception as exc:
            logger.warning("格式化市场数据失败: %s", exc)
            return "市场数据解析失败"

    def _format_account_info(self, portfolio: Optional[Portfolio]) -> str:
        """格式化账户总览信息"""
        if not portfolio:
            return "无组合信息"

        # 计算风险暴露
        total_positions_value = sum(p.value for p in portfolio.positions)
        risk_exposure = (
            (total_positions_value / portfolio.total_value * 100)
            if portfolio.total_value > 0
            else 0
        )

        return (
            f"账户总览:\n"
            f"  钱包余额: {portfolio.wallet_balance} USDT\n"
            f"  可用余额: {portfolio.available_balance} USDT\n"
            f"  保证金余额: {portfolio.margin_balance} USDT\n"
            f"  持仓总值: {total_positions_value} USDT\n"
            f"  持仓数量: {len(portfolio.positions)} 个\n"
            f"  未实现盈亏: {portfolio.unrealized_pnl} USDT\n"
            f"  风险暴露: {risk_exposure:.2f}%\n"
            f"  今日盈亏: {portfolio.daily_pnl} USDT\n"
            f"  累计收益率: {portfolio.total_return:.2f}%"
        )

    async def _build_batch_context_with_regime(
        self,
        market_regime: MarketRegime,
        symbols_snapshots: Dict[str, Dict[str, Any]],
        portfolio: Optional[Portfolio] = None,
    ) -> Dict[str, Any]:
        """构建包含市场状态的批量分析上下文"""
        # 账户信息
        account_info = self._format_account_info(portfolio)

        # 每个币种的数据和持仓
        symbols_data = {}
        portfolio_positions = {}

        for symbol, snapshot in symbols_snapshots.items():
            # 格式化市场数据
            market_data = self._format_market_snapshot(snapshot)
            symbols_data[symbol] = {"market_data": market_data}

            # 格式化持仓信息
            position_info = self._format_position_info(symbol, portfolio)
            portfolio_positions[symbol] = position_info

        # 添加风控参数 (从配置读取)
        from src.core.config import get_config
        import time
        config = get_config()
        risk_config = config.get_risk_config()

        # 计算持仓时长
        current_time_ms = int(time.time() * 1000)
        position_durations = {}
        if portfolio_positions:
            for symbol, pos_str in portfolio_positions.items():
                # 尝试从position对象获取opened_at
                # 由于我们传入的是字符串,需要获取原始Position对象
                pass  # 暂时跳过,在后面的持仓信息中添加

        return {
            "market_regime": market_regime,
            "symbols_data": symbols_data,
            "account_info": account_info,
            "portfolio_positions": portfolio_positions,
            "risk_params": {
                "max_position_size": float(risk_config.max_position_size * Decimal("100")),  # 转为百分比
                "max_daily_loss": float(risk_config.max_daily_loss * Decimal("100")),
                "stop_loss_percentage": float(risk_config.stop_loss_percentage),
                "take_profit_percentage": float(risk_config.take_profit_percentage),
            },
            "trading_intervals": {
                "trader_interval_seconds": config.trader_interval,  # 战术层决策间隔
                "strategist_interval_seconds": config.strategist_interval,  # 战略层决策间隔
                "current_timestamp_ms": current_time_ms,  # 当前时间戳用于计算持仓时长
            },
        }

    def _build_regime_aware_prompt(self, context: Dict[str, Any]) -> str:
        """构建包含市场状态的提示词"""
        regime: MarketRegime = context["market_regime"]
        symbols_data = context["symbols_data"]
        account_info = context["account_info"]
        portfolio_positions = context["portfolio_positions"]
        risk_params = context.get("risk_params", {})

        # 构建市场状态摘要
        regime_summary = f"""
## 战略层市场判断

{regime.get_summary()}

**市场叙事**: {regime.market_narrative}

**关键驱动因素**:
{chr(10).join(f"- {driver}" for driver in regime.key_drivers)}

**交易模式**: {regime.trading_mode}
**建议持仓周期**: {regime.time_horizon.value}
**仓位调整系数**: {regime.position_sizing_multiplier}x
**建议现金比例**: {regime.cash_ratio:.0%}

**币种筛选结果**:
- 推荐关注: {', '.join(regime.recommended_symbols[:10])}
- 黑名单: {', '.join(regime.blacklist_symbols) if regime.blacklist_symbols else '无'}

**战略判断理由**:
{regime.reasoning}
"""

        # 构建币种市场数据
        symbols_info = []
        for symbol, data in symbols_data.items():
            symbols_info.append(f"### {symbol}")
            symbols_info.append(data["market_data"])
            symbols_info.append("")

        # 使用模板配置
        from src.decision.prompt_templates import PromptTemplateConfig, PromptStyle
        from src.core.config import get_config

        config = get_config()
        try:
            style = PromptStyle(config.prompt_style)
        except ValueError:
            style = PromptStyle.BALANCED

        # 模板已经使用 %s 预填充了配置，直接替换数据占位符
        template = PromptTemplateConfig.get_trader_user_template(style)

        # 格式化持仓信息
        positions_str = chr(10).join(
            f"{symbol}: {pos}" for symbol, pos in portfolio_positions.items()
        ) if portfolio_positions else "无"

        prompt = (template
            .replace("{regime}", regime.regime.value)
            .replace("{risk_level}", regime.risk_level.value)
            .replace("{trading_mode}", regime.trading_mode)
            .replace("{position_multiplier}", str(regime.position_sizing_multiplier))
            .replace("{cash_ratio}", f"{regime.cash_ratio:.0%}")
            .replace("{market_narrative}", regime.market_narrative)
            .replace("{key_drivers}", ', '.join(regime.key_drivers[:3]))
            .replace("{recommended_symbols}", ', '.join(regime.recommended_symbols[:5]))
            .replace("{account_info}", account_info)
            .replace("{portfolio_positions}", positions_str)
            .replace("{symbols_info}", chr(10).join(symbols_info))
            .replace("{max_position_size}", f"{risk_params.get('max_position_size', 20):.0f}")
        )

        return prompt

    async def _build_batch_context(
        self,
        symbols_snapshots: Dict[str, Dict[str, Any]],
        strategy: StrategyConfig,
        portfolio: Optional[Portfolio] = None,
    ) -> Dict[str, Any]:
        """构建批量分析的上下文"""
        # 账户信息
        account_info = self._format_account_info(portfolio)

        # 风险参数
        risk_params = {
            "max_position_size": float(strategy.max_position_size * Decimal("100")),
            "max_single_trade": float(strategy.max_single_trade),
            "stop_loss_percentage": float(strategy.stop_loss_percentage),
            "take_profit_percentage": float(strategy.take_profit_percentage),
        }

        # 每个币种的数据和持仓
        symbols_data = {}
        portfolio_positions = {}

        for symbol, snapshot in symbols_snapshots.items():
            # 格式化市场数据
            market_data = self._format_market_snapshot(snapshot)
            symbols_data[symbol] = {"market_data": market_data}

            # 格式化持仓信息
            position_info = self._format_position_info(symbol, portfolio)
            portfolio_positions[symbol] = position_info

        return {
            "symbols_data": symbols_data,
            "strategy": strategy.description,
            "risk_params": risk_params,
            "account_info": account_info,
            "portfolio_positions": portfolio_positions,
        }

    def _parse_batch_signals(
        self,
        response: LLMResponse,
        expected_symbols: set,
    ) -> Dict[str, Optional[TradingSignal]]:
        """解析批量信号响应"""
        signals: Dict[str, Optional[TradingSignal]] = {}

        try:
            content = response.content or ""

            # 尝试提取JSON数组
            import re
            json_match = re.search(r'\[[\s\S]*\]', content)
            if not json_match:
                logger.error("批量响应中未找到JSON数组")
                return {symbol: None for symbol in expected_symbols}

            signals_data = json.loads(json_match.group())

            if not isinstance(signals_data, list):
                logger.error("批量响应不是数组格式")
                return {symbol: None for symbol in expected_symbols}

            # 创建符号映射表：BTC/USDT → BTC/USDT:USDT
            symbol_map = {}
            for expected in expected_symbols:
                # 如果是永续合约格式 (包含 :USDT)
                if ':USDT' in expected:
                    # 提取基础符号 BTC/USDT
                    base_symbol = expected.split(':')[0]
                    symbol_map[base_symbol] = expected
                    symbol_map[expected] = expected
                else:
                    symbol_map[expected] = expected

            # 解析每个信号
            for signal_dict in signals_data:
                try:
                    llm_symbol = signal_dict.get("symbol")
                    if not llm_symbol:
                        continue

                    # 映射 LLM 返回的符号到期望的符号格式
                    symbol = symbol_map.get(llm_symbol)
                    if not symbol:
                        logger.warning("LLM 返回的符号 %s 无法映射到期望的符号", llm_symbol)
                        continue

                    # 解析信号类型
                    signal_type_str = signal_dict.get("signal_type", "hold")
                    signal_type = _parse_signal_type(signal_type_str)

                    # 生成时间戳
                    now = datetime.now(tz=timezone.utc)
                    timestamp = int(now.timestamp() * 1000)

                    # 构建信号
                    signal = TradingSignal(
                        timestamp=timestamp,
                        dt=now,
                        symbol=symbol,
                        signal_type=signal_type,
                        confidence=float(signal_dict.get("confidence", 0.5)),
                        suggested_price=Decimal(str(signal_dict["suggested_price"]))
                        if signal_dict.get("suggested_price")
                        else None,
                        suggested_amount=Decimal(str(signal_dict["suggested_amount"]))
                        if signal_dict.get("suggested_amount")
                        else None,
                        stop_loss=Decimal(str(signal_dict["stop_loss"]))
                        if signal_dict.get("stop_loss")
                        else None,
                        take_profit=Decimal(str(signal_dict["take_profit"]))
                        if signal_dict.get("take_profit")
                        else None,
                        leverage=int(signal_dict["leverage"])
                        if signal_dict.get("leverage")
                        else None,
                        reasoning=signal_dict.get("reasoning", "批量分析生成的信号"),
                        supporting_factors=signal_dict.get("supporting_factors", []),
                        risk_factors=signal_dict.get("risk_factors", []),
                        source="batch_trader",
                    )

                    signals[symbol] = signal
                    # Hold 信号特殊处理：0 置信度表示"观望，无明确机会"
                    if signal_type == SignalType.HOLD and signal.confidence == 0.0:
                        logger.info(
                            "解析信号: %s → %s (保持观望，无明确机会)",
                            symbol,
                            signal_type.value,
                        )
                    else:
                        logger.info(
                            "解析信号: %s → %s (置信度: %.2f)",
                            symbol,
                            signal_type.value,
                            signal.confidence,
                        )

                except Exception as exc:
                    logger.error("解析单个信号失败: %s", exc)
                    continue

            # 为缺失的币种添加 None
            for symbol in expected_symbols:
                if symbol not in signals:
                    logger.warning("%s 未在批量响应中找到，设为 None", symbol)
                    signals[symbol] = None

        except Exception as exc:
            logger.error("解析批量响应失败: %s", exc, exc_info=True)
            return {symbol: None for symbol in expected_symbols}

        return signals

    async def _chat_with_tools(self, messages: List[Message]) -> LLMResponse:
        """Standard tool-handling loop for the trader."""
        history = list(messages)
        tool_schemas = self.tools.get_all_schemas() if self.tools else None

        used_tools: set[str] = set()
        response: Optional[LLMResponse] = None
        for iteration in range(self.max_tool_iterations):
            response = await self.llm.chat(history, tools=tool_schemas, temperature=0.2, max_tokens=1800)
            if not response.tool_calls:
                return response

            history.append(
                Message(role="assistant", content=response.content, tool_calls=response.tool_calls)
            )

            if not self.tools:
                logger.warning("LLM 请求调用工具，但当前未注册任何工具。")
                continue

            for call in response.tool_calls:
                await self._handle_tool_call(history, call)
                used_tools.add(call.name)

            # 每次工具调用后提示，但策略有所不同
            if iteration < self.max_tool_iterations - 2:
                # 前几轮：温和提示
                history.append(
                    Message(
                        role="system",
                        content="如果已获取足够数据，请输出交易信号JSON；否则可继续使用工具。"
                    )
                )
            else:
                # 最后1-2轮：强烈提示
                history.append(
                    Message(
                        role="system",
                        content=(
                            "⚠️ 已接近工具调用上限。请基于现有数据立即输出交易信号JSON，"
                            "格式：{\"signal_type\": ..., \"confidence\": ..., ...}，不要继续调用工具。"
                        ),
                    )
                )

        if response is None:
            raise DecisionError("LLM 未返回有效的交易信号。")

        logger.info("Trader调用工具达到 %s 次上限，触发fallback生成信号。", self.max_tool_iterations)
        # 尝试触发一次最终回答
        history.append(
            Message(
                role="system",
                content=(
                    "请立即输出最终的JSON决策结果，无需再调用工具。"
                    "格式严格为JSON对象。"
                ),
            )
        )
        fallback = await self.llm.chat(history, tools=None, temperature=0.0, max_tokens=800)
        return fallback

    async def _handle_tool_call(self, history: List[Message], tool_call: ToolCall) -> None:
        if not self.tools:
            return

        try:
            result = await self.tools.execute_tool(tool_call.name, **tool_call.arguments)
        except ToolExecutionError as exc:
            logger.error("Trader 工具执行失败: %s", exc)
            result = {"error": str(exc)}

        history.append(
            Message(
                role="tool",
                name=tool_call.name,
                tool_call_id=tool_call.id,
                content=json.dumps(result, ensure_ascii=False, default=str),
            )
        )


def _try_parse_json(content: str | None) -> Dict[str, Any]:
    """
    尝试从LLM响应中提取JSON对象

    支持的格式：
    1. 纯JSON对象
    2. Markdown代码块中的JSON
    3. 包含注释的JSON
    4. 文本中嵌入的JSON对象
    """
    if not content:
        return {}

    raw = content.strip()

    # 1. 移除markdown代码块标记
    if raw.startswith("```"):
        lines = raw.splitlines()
        if len(lines) >= 2 and lines[0].startswith("```"):
            raw = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])
            raw = raw.strip()

    # 2. 尝试直接解析
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # 3. 移除单行注释后重试
    if "//" in raw:
        raw = raw.split("//", 1)[0].strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass

    # 4. 尝试从文本中提取JSON对象（查找第一个 { 到最后一个 } 之间的内容）
    import re
    json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', content, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            pass

    # 5. 记录警告并返回空字典
    logger.warning(
        f"LLM trader response not valid JSON, using fallback parsing. "
        f"Content preview: {content[:200] if content else 'empty'}..."
    )
    return {}


def _format_cases(experiences: Any) -> str:
    if not experiences:
        return "暂无相关案例"

    cases = []
    for idx, item in enumerate(experiences, start=1):
        if isinstance(item, dict):
            situation = item.get("situation", "未知情景")
            decision = item.get("decision", "未知决策")
            outcome = item.get("outcome", "未知结果")
        else:
            situation = getattr(item, "situation", "未知情景")
            decision = getattr(item, "decision", "未知决策")
            outcome = getattr(item, "outcome", "未知结果")

        cases.append(f"{idx}. 情景: {situation} | 决策: {decision} | 结果: {outcome}")

    return "\n".join(cases)
