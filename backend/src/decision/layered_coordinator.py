"""
Layered Decision Coordinator

协调战略层(Strategist)和战术层(Trader)的双层决策循环
"""

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.core.logger import get_logger
from src.decision.strategist import LLMStrategist
from src.decision.trader import LLMTrader
from src.models.regime import MarketRegime
from src.models.portfolio import Portfolio
from src.models.decision import TradingSignal
from src.perception.environment_builder import EnvironmentBuilder

logger = get_logger(__name__)


class LayeredDecisionCoordinator:
    """
    双层决策协调器

    职责:
    1. 每小时调用战略层分析市场环境,生成 MarketRegime
    2. 每3-5分钟调用战术层根据 MarketRegime 生成交易信号
    3. 缓存 MarketRegime 供战术层使用
    """

    def __init__(
        self,
        strategist: LLMStrategist,
        trader: LLMTrader,
        environment_builder: EnvironmentBuilder,
        *,
        strategist_interval_seconds: int = 3600,  # 1小时
        trader_interval_seconds: int = 180,  # 3分钟
        database_manager: Optional[Any] = None,  # 数据库管理器
        shock_detection_enabled: bool = True,
        shock_atr_multiple: float = 2.0,
        shock_min_move_pct: float = 1.0,
        shock_cooldown_seconds: int = 300,
    ):
        self.strategist = strategist
        self.trader = trader
        self.environment_builder = environment_builder
        self.strategist_interval = strategist_interval_seconds
        self.trader_interval = trader_interval_seconds
        self.db_manager = database_manager

        # 缓存当前的市场状态判断
        self.current_regime: Optional[MarketRegime] = None
        self.last_strategist_run: Optional[datetime] = None
        self.shock_detection_enabled = shock_detection_enabled
        self.shock_atr_multiple = shock_atr_multiple
        self.shock_min_move_pct = shock_min_move_pct
        self.shock_cooldown_seconds = shock_cooldown_seconds
        self.last_shock_trigger: Optional[datetime] = None

    async def run_strategist_cycle(
        self,
        crypto_overview: Optional[Dict[str, Any]] = None,
        trigger_reason: Optional[str] = None,
    ) -> MarketRegime:
        """
        运行战略层分析周期

        1. 采集市场环境数据
        2. LLM 分析生成 MarketRegime
        3. 缓存结果供战术层使用

        Args:
            crypto_overview: 加密市场概览数据(可选)

        Returns:
            MarketRegime: 市场状态判断
        """
        import time
        start_time = time.time()

        logger.info("=" * 80)
        logger.info("战略层分析周期开始")
        if trigger_reason:
            logger.info("触发原因: %s", trigger_reason)
        logger.info("=" * 80)

        try:
            # 1. 采集市场环境
            logger.info("[计时] 开始构建市场环境...")
            t1 = time.time()
            environment = await self.environment_builder.build_environment()
            t2 = time.time()
            logger.info(f"[计时] 市场环境构建完成，耗时: {t2-t1:.2f}秒")

            if not environment.is_ready_for_analysis():
                logger.warning(
                    f"市场环境数据不完整 (完整度: {environment.data_completeness:.0%}), "
                    "继续使用缓存的 regime 或生成保守的 regime"
                )

            # 2. 战略层分析
            logger.info("[计时] 开始战略层LLM推理...")
            t3 = time.time()
            regime = await self.strategist.analyze_market_with_environment(
                environment=environment,
                crypto_overview=crypto_overview,
            )
            t4 = time.time()
            logger.info(f"[计时] 战略层LLM推理完成，耗时: {t4-t3:.2f}秒")

            # 3. 缓存结果
            self.current_regime = regime
            self.last_strategist_run = datetime.now(timezone.utc)
            if trigger_reason:
                self.last_shock_trigger = self.last_strategist_run

            logger.info("战略层分析完成: %s", regime.get_summary())
            logger.info("有效期至: %s", datetime.fromtimestamp(regime.valid_until / 1000))

            # 4. 保存战略层决策到数据库
            logger.info("[计时] 开始保存战略决策到数据库...")
            t5 = time.time()
            await self._save_strategic_decision(regime, environment)
            t6 = time.time()
            logger.info(f"[计时] 战略决策保存完成，耗时: {t6-t5:.2f}秒")

            total_time = time.time() - start_time
            logger.info(f"[计时] 战略层周期总耗时: {total_time:.2f}秒")

            return regime

        except Exception as exc:
            logger.error(f"战略层分析失败: {exc}", exc_info=True)
            # 返回之前的 regime 或生成一个保守的默认 regime
            if self.current_regime and self.current_regime.is_valid():
                logger.info("使用缓存的 regime")
                return self.current_regime
            else:
                logger.warning("生成保守的默认 regime")
                return self._create_default_regime()

    async def run_trader_cycle(
        self,
        symbols_snapshots: Dict[str, Dict[str, Any]],
        portfolio: Optional[Portfolio] = None,
    ) -> Dict[str, Optional[TradingSignal]]:
        """
        运行战术层决策周期

        1. 检查 MarketRegime 是否有效
        2. 根据 regime 筛选币种
        3. 生成交易信号

        Args:
            symbols_snapshots: {symbol: market_snapshot}
            portfolio: 当前持仓

        Returns:
            {symbol: TradingSignal or None}
        """
        logger.info("=" * 80)
        logger.info("战术层决策周期开始")
        logger.info("=" * 80)

        try:
            # 1. 检查 regime
            if not self.current_regime:
                logger.warning("尚无有效的 MarketRegime, 先运行战略层分析")
                return {}

            if not self.current_regime.is_valid():
                logger.warning("MarketRegime 已过期, 需要重新运行战略层分析")
                # 可以选择等待或使用过期的 regime
                # 这里选择使用过期的 regime 但记录警告
                logger.info("使用过期的 regime 继续交易 (降低置信度)")

            filtered_snapshots = symbols_snapshots
            logger.info(f"战术层分析币种: {list(filtered_snapshots.keys())}")

            # 3. 生成交易信号
            signals = await self.trader.batch_generate_signals_with_regime(
                market_regime=self.current_regime,
                symbols_snapshots=filtered_snapshots,
                portfolio=portfolio,
            )

            logger.info("战术层决策完成")

            # 4. 保存战术层信号到数据库(包含完整上下文)
            await self._save_trading_signals(signals, filtered_snapshots, portfolio)

            # 注意: 持仓快照的保存已移到交易执行后 (trading_coordinator.py)
            # 这样可以保存执行后的真实持仓状态，而不是执行前的旧状态

            return signals

        except Exception as exc:
            logger.error(f"战术层决策失败: {exc}", exc_info=True)
            return {}

    def detect_market_shock(
        self,
        snapshots: Dict[str, Dict[str, Any]],
    ) -> Optional[str]:
        """
        检测短周期异常波动以触发战略层刷新。
        使用 15m 行情：若价格变化超过 ATR 指定倍数且涨跌幅达到阈值，则返回原因。
        """
        if not self.shock_detection_enabled or not snapshots:
            return None

        now = datetime.now(timezone.utc)
        if self.last_shock_trigger:
            if (now - self.last_shock_trigger).total_seconds() < self.shock_cooldown_seconds:
                return None

        if self.last_strategist_run:
            if (now - self.last_strategist_run).total_seconds() < self.shock_cooldown_seconds:
                return None

        for symbol, snapshot in snapshots.items():
            mid_term = snapshot.get("mid_term") or {}
            if not mid_term:
                continue

            change_abs = mid_term.get("change_abs")
            atr_value = mid_term.get("atr")
            change_pct = mid_term.get("change_pct")

            if change_abs is None or atr_value in (None, 0):
                continue

            atr = float(atr_value)
            if atr <= 0:
                continue

            abs_change = abs(float(change_abs))
            pct_change = abs(float(change_pct or 0))

            if pct_change < self.shock_min_move_pct:
                continue

            if abs_change >= self.shock_atr_multiple * atr:
                ratio = abs_change / atr if atr else 0
                direction = "上涨" if float(change_abs) > 0 else "下跌"
                reason = (
                    f"{symbol} 15m{direction}{float(change_pct or 0):+.2f}% "
                    f"≈ {ratio:.1f}×ATR"
                )
                self.last_shock_trigger = now
                return reason

        return None

    async def start_dual_loop(
        self,
        get_crypto_overview_func,
        get_symbols_snapshots_func,
        get_portfolio_func,
        signal_handler_func,
    ):
        """
        启动双层决策循环

        Args:
            get_crypto_overview_func: 获取加密市场概览的函数
            get_symbols_snapshots_func: 获取币种快照的函数
            get_portfolio_func: 获取持仓的函数
            signal_handler_func: 处理交易信号的函数
        """
        logger.info("✓ [分层决策] 双层决策循环已启动")
        logger.info(f"战略层周期: {self.strategist_interval}秒")
        logger.info(f"战术层周期: {self.trader_interval}秒")

        # 先运行一次战略层分析
        crypto_overview = await get_crypto_overview_func()
        await self.run_strategist_cycle(crypto_overview)

        # 启动两个并发循环
        strategist_task = asyncio.create_task(
            self._strategist_loop(get_crypto_overview_func)
        )
        trader_task = asyncio.create_task(
            self._trader_loop(
                get_symbols_snapshots_func,
                get_portfolio_func,
                signal_handler_func,
            )
        )

        await asyncio.gather(strategist_task, trader_task)

    async def _strategist_loop(self, get_crypto_overview_func):
        """战略层循环 (每小时)"""
        while True:
            try:
                await asyncio.sleep(self.strategist_interval)
                crypto_overview = await get_crypto_overview_func()
                await self.run_strategist_cycle(crypto_overview)
            except Exception as exc:
                logger.error(f"战略层循环异常: {exc}", exc_info=True)

    async def _trader_loop(
        self,
        get_symbols_snapshots_func,
        get_portfolio_func,
        signal_handler_func,
    ):
        """战术层循环 (每3-5分钟)"""
        while True:
            try:
                await asyncio.sleep(self.trader_interval)

                snapshots = await get_symbols_snapshots_func()
                portfolio = await get_portfolio_func()

                signals = await self.run_trader_cycle(snapshots, portfolio)

                # 处理信号
                if signals:
                    await signal_handler_func(signals)

            except Exception as exc:
                logger.error(f"战术层循环异常: {exc}", exc_info=True)

    def should_run_strategist(self) -> bool:
        """
        判断是否应该运行战略层分析

        Returns:
            True if should run, False otherwise
        """
        if not self.last_strategist_run:
            # 从未运行过，应该运行
            return True

        now = datetime.now(timezone.utc)
        elapsed = (now - self.last_strategist_run).total_seconds()

        return elapsed >= self.strategist_interval

    def _create_default_regime(self) -> MarketRegime:
        """创建保守的默认市场状态"""
        from src.models.regime import MarketBias, MarketStructure, RiskLevel, TimeHorizon

        now = datetime.now(timezone.utc)
        timestamp = int(now.timestamp() * 1000)

        return MarketRegime(
            bias=MarketBias.NEUTRAL,
            confidence=0.3,
            market_structure=MarketStructure.RANGING,
            risk_level=RiskLevel.MEDIUM,
            market_narrative="无有效市场环境数据,采用保守策略",
            key_drivers=["数据不完整"],
            time_horizon=TimeHorizon.SHORT,
            cash_ratio=0.7,  # 保守:70%现金
            volatility_range="medium",
            max_exposure=0.4,
            trading_mode="conservative",
            position_sizing_multiplier=0.5,  # 减半仓位
            timestamp=timestamp,
            dt=now,
            valid_until=timestamp + 3600 * 1000,
            reasoning="市场环境数据采集失败,采用保守的默认策略",
        )

    async def _save_strategic_decision(
        self,
        regime: MarketRegime,
        environment: Any,
    ) -> None:
        """保存战略层决策到数据库"""
        if not self.db_manager:
            return

        try:
            from src.services.database import TradingDAO
            from src.models.decision import DecisionRecord
            import uuid
            import json

            # 构建决策记录
            decision_id = f"strategic_{uuid.uuid4().hex[:12]}"

            # 输入上下文
            input_context = {
                "environment_data_completeness": environment.data_completeness if environment else 0.0,
                "environment_summary": environment.get_summary() if environment else "",
            }

            # 添加宏观数据摘要
            if environment and environment.macro:
                input_context["macro_data"] = {
                    "fed_rate": environment.macro.fed_rate,
                    "dxy_change_24h": environment.macro.dxy_change_24h,
                }

            # 添加情绪数据摘要
            if environment and environment.sentiment:
                input_context["sentiment"] = {
                    "fear_greed_index": environment.sentiment.fear_greed_index,
                    "fear_greed_label": environment.sentiment.fear_greed_label,
                }

            # 决策内容（MarketRegime的JSON表示）
            decision_content = {
                "bias": regime.bias.value,
                "market_structure": regime.market_structure.value,
                "confidence": regime.confidence,
                "risk_level": regime.risk_level.value,
                "market_narrative": regime.market_narrative,
                "key_drivers": regime.key_drivers,
                "time_horizon": regime.time_horizon.value,
                "cash_ratio": float(regime.cash_ratio),
                "volatility_range": regime.volatility_range,
                "max_exposure": float(regime.max_exposure) if regime.max_exposure is not None else None,
                "trading_mode": regime.trading_mode,
                "position_sizing_multiplier": float(regime.position_sizing_multiplier),
            }

            decision_record = DecisionRecord(
                id=decision_id,
                timestamp=regime.timestamp,
                dt=regime.dt,
                input_context=input_context,
                thought_process=regime.reasoning,
                tools_used=[],
                decision=json.dumps(decision_content, ensure_ascii=False),
                action_taken=f"偏向: {regime.bias.value}, 结构: {regime.market_structure.value}",
                decision_layer="strategic",
                model_used=self.strategist.llm.model,  # 从实际使用的LLM客户端获取
                tokens_used=None,
                latency_ms=None,
            )

            # 保存到数据库
            async with self.db_manager.get_session() as session:
                dao = TradingDAO(session)
                await dao.save_decision(decision_record)
                logger.debug(f"✅ 战略层决策已保存: {decision_id}")

        except Exception as exc:
            logger.warning(f"保存战略层决策失败: {exc}")

    async def _save_trading_signals(
        self,
        signals: Dict[str, Optional[TradingSignal]],
        snapshots: Dict[str, Dict[str, Any]] = None,
        portfolio: 'Portfolio' = None,
    ) -> None:
        """保存战术层交易信号到数据库"""
        if not self.db_manager or not signals:
            return

        try:
            from src.services.database import TradingDAO
            from src.models.decision import DecisionRecord
            import uuid
            import json
            from decimal import Decimal

            # 为每个信号创建决策记录
            async with self.db_manager.get_session() as session:
                dao = TradingDAO(session)

                for symbol, signal in signals.items():
                    if signal is None:
                        continue

                    decision_id = f"tactical_{uuid.uuid4().hex[:12]}"

                    # 构建完整的输入上下文
                    input_context = {
                        "symbol": symbol,
                        # 战略信息
                        "bias": self.current_regime.bias.value if self.current_regime else "unknown",
                        "market_structure": self.current_regime.market_structure.value if self.current_regime else "unknown",
                        "risk_level": self.current_regime.risk_level.value if self.current_regime else "unknown",
                        "trading_mode": self.current_regime.trading_mode if self.current_regime else "unknown",
                        "cash_ratio": float(self.current_regime.cash_ratio) if self.current_regime else None,
                        "position_multiplier": float(self.current_regime.position_sizing_multiplier) if self.current_regime else None,
                        # 市场数据
                        "market_snapshot": {},
                        # 账户信息
                        "portfolio": {},
                    }

                    # 添加市场快照
                    if snapshots and symbol in snapshots:
                        snapshot = snapshots[symbol]
                        input_context["market_snapshot"] = {
                            "latest_price": str(snapshot.get("latest_price", "")) if snapshot.get("latest_price") else None,
                            # 其他市场数据可以选择性添加，避免太大
                        }

                    # 添加账户信息
                    if portfolio:
                        input_context["portfolio"] = {
                            "total_value": str(portfolio.total_value),
                            "cash": str(portfolio.cash),
                            "positions_count": len(portfolio.positions),
                            "daily_pnl": str(portfolio.daily_pnl),
                        }

                        # 如果有该币种的持仓，添加持仓信息
                        position = portfolio.get_position(symbol)
                        if position:
                            input_context["existing_position"] = {
                                "side": position.side.value,
                                "amount": str(position.amount),
                                "entry_price": str(position.entry_price),
                                "current_price": str(position.current_price) if position.current_price else None,
                                "unrealized_pnl": str(position.unrealized_pnl),
                                "unrealized_pnl_pct": str(position.unrealized_pnl_percentage),
                                "leverage": position.leverage,
                            }

                    # 决策内容
                    decision_content = {
                        "signal_type": signal.signal_type.value,
                        "confidence": signal.confidence,
                        "suggested_price": str(signal.suggested_price) if signal.suggested_price else None,
                        "suggested_amount": str(signal.suggested_amount) if signal.suggested_amount else None,
                        "stop_loss": str(signal.stop_loss) if signal.stop_loss else None,
                        "take_profit": str(signal.take_profit) if signal.take_profit else None,
                        "supporting_factors": signal.supporting_factors,
                        "risk_factors": signal.risk_factors,
                    }

                    decision_record = DecisionRecord(
                        id=decision_id,
                        timestamp=signal.timestamp,
                        dt=signal.dt,
                        input_context=input_context,
                        thought_process=signal.reasoning,
                        tools_used=[],
                        decision=json.dumps(decision_content, ensure_ascii=False),
                        action_taken=f"{signal.signal_type.value} @ {signal.suggested_price}",
                        decision_layer="tactical",
                        model_used=self.trader.llm.model,  # 从实际使用的LLM客户端获取
                        tokens_used=None,
                        latency_ms=None,
                    )

                    await dao.save_decision(decision_record)

                # 统计各类信号数量
                signal_counts = {}
                for s in signals.values():
                    if s:
                        signal_type = s.signal_type.value
                        signal_counts[signal_type] = signal_counts.get(signal_type, 0) + 1

                count_str = ", ".join([f"{k}: {v}" for k, v in signal_counts.items()])
                logger.debug(f"✅ 战术层信号已保存: {len([s for s in signals.values() if s])} 个 ({count_str})")

        except Exception as exc:
            logger.warning(f"保存战术层信号失败: {exc}")

    async def _save_snapshots(
        self,
        portfolio: "Portfolio",
    ) -> None:
        """保存持仓快照和投资组合快照

        Args:
            portfolio: 投资组合对象
        """
        if not self.db_manager or not portfolio:
            return

        # AccountSyncService 已负责 positions/closed_positions/portfolio_snapshots 的写入，
        # 这里不再重复保存，避免交换所ID不一致。
        return

    async def close(self):
        """关闭资源"""
        await self.environment_builder.close()
