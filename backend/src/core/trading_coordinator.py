#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Trading Coordinator

交易协调器,负责整个交易系统的流程编排和协调。
将主循环逻辑从 main.py 中分离,提高代码的可维护性。
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple
from decimal import Decimal

from src.models.decision import StrategyConfig, TradingSignal, SignalType
from src.models.portfolio import Portfolio
from src.services.market_data import MarketDataCollector
from src.execution.trading_executor import TradingExecutor
from src.execution.portfolio import PortfolioManager
from src.core.config import Config
from src.core.exceptions import TradingSystemError


class TradingCoordinator:
    """
    交易协调器

    职责:
    1. 协调数据采集、决策生成、交易执行
    2. 管理传统模式和分层决策模式的主循环
    3. 处理系统启动和关闭
    """

    def __init__(
        self,
        config: Config,
        data_collector: MarketDataCollector,
        trading_executor: TradingExecutor,
        portfolio_manager: PortfolioManager,
        decision_maker: Optional[Any] = None,  # LLMTrader or simple rules
        layered_coordinator: Optional[Any] = None,  # LayeredDecisionCoordinator
        market_analyzer: Optional[Any] = None,  # MarketAnalyzer
        account_sync_service: Optional[Any] = None,  # AccountSyncService
        performance_service: Optional[Any] = None,  # PerformanceService
        logger: Optional[logging.Logger] = None,
    ):
        """
        初始化交易协调器

        Args:
            config: 系统配置
            data_collector: 数据采集服务
            trading_executor: 交易执行服务
            portfolio_manager: 投资组合管理器
            decision_maker: 决策生成器 (传统模式)
            layered_coordinator: 分层决策协调器 (分层模式)
            market_analyzer: 市场分析器 (技术指标→简洁摘要)
            account_sync_service: 账户同步服务
            performance_service: 绩效服务
            logger: 日志记录器
        """
        self.config = config
        self.data_collector = data_collector
        self.trading_executor = trading_executor
        self.portfolio_manager = portfolio_manager
        self.decision_maker = decision_maker
        self.layered_coordinator = layered_coordinator
        self.market_analyzer = market_analyzer
        self.account_sync_service = account_sync_service
        self.performance_service = performance_service
        self.logger = logger or logging.getLogger(__name__)

        self.running = False
        self.symbols = data_collector.symbols

    async def run_layered_decision_mode(self):
        """分层决策模式的主循环"""
        try:
            if not self.portfolio_manager or not self.layered_coordinator:
                raise TradingSystemError("分层决策系统尚未初始化。")

            self.running = True
            self.logger.info("\n" + "=" * 60)
            self.logger.info("✓ [分层决策] 主循环已启动")
            self.logger.info("=" * 60)

            if not self.config.enable_trading:
                self.logger.warning("当前处于纸面交易模式（未启用真实下单）。")

            # 启动数据采集服务
            await self.data_collector.start()

            # 启动绩效服务
            if self.performance_service:
                await self.performance_service.start()
                self.logger.info("✓ [绩效服务] 已启动")

            # 首次运行战略层分析
            await self._run_initial_strategist_cycle()

            # 战术层主循环
            trader_cycles = 0
            strategist_interval_cycles = self.config.strategist_interval // self.config.trader_interval
            self.logger.info(
                f"[循环配置] 战略层间隔: {self.config.strategist_interval}秒, "
                f"战术层间隔: {self.config.trader_interval}秒, "
                f"每 {strategist_interval_cycles} 个战术周期执行一次战略分析"
            )

            while self.running:
                trader_cycles += 1

                # 定期运行战略层
                if trader_cycles % strategist_interval_cycles == 0:
                    self.logger.info(f"[战略触发] 第 {trader_cycles} 个战术周期，触发战略层分析")
                    await self._run_strategist_cycle()
                    trader_cycles = 0
                else:
                    # 每10个周期记录一次进度
                    if trader_cycles % 10 == 0:
                        remaining = strategist_interval_cycles - trader_cycles
                        self.logger.debug(
                            f"[战略倒计时] 第 {trader_cycles}/{strategist_interval_cycles} 个周期, "
                            f"还有 {remaining} 个周期后执行战略分析"
                        )

                # 1. 收集市场数据快照
                snapshots = await self._collect_snapshots()
                if not snapshots:
                    self.logger.warning("所有交易对都没有缓存数据，跳过本轮")
                    await self._interruptible_sleep(max(1, self.config.trader_interval))
                    continue

                # 2. 获取当前投资组合
                portfolio = await self.portfolio_manager.get_current_portfolio()

                # 3. 运行战术层生成交易信号
                try:
                    signals = await self.layered_coordinator.run_trader_cycle(
                        symbols_snapshots=snapshots,
                        portfolio=portfolio,
                    )
                    self.logger.info("✅ 战术层分析完成，收到 %d 个信号", len(signals) if signals else 0)
                except Exception as exc:
                    self.logger.error("战术层分析失败: %s", exc, exc_info=True)
                    await self._interruptible_sleep(max(1, self.config.trader_interval))
                    continue

                if not signals:
                    self.logger.info("📊 本轮无交易信号")
                    await self._interruptible_sleep(max(1, self.config.trader_interval))
                    continue

                # 4. 获取策略配置
                strategy = await self._make_strategy(portfolio, next(iter(snapshots.values())))
                if strategy is None:
                    self.logger.warning("策略生成失败，跳过本轮")
                    await self._interruptible_sleep(max(1, self.config.trader_interval))
                    continue

                # 5. 执行交易信号
                latest_portfolio = await self._execute_signals(
                    signals, snapshots, strategy, portfolio
                )

                # 6. 如果执行了交易，保存快照
                try:
                    if latest_portfolio:
                        # 只有在执行了交易时才保存快照
                        if self.layered_coordinator:
                            await self.layered_coordinator._save_snapshots(latest_portfolio)
                            self.logger.info("✅ 交易执行后快照已保存")
                    else:
                        self.logger.debug("本轮无交易执行，跳过快照保存（由 AccountSyncService 持续同步）")
                except Exception as exc:
                    self.logger.error("保存执行后快照失败: %s", exc, exc_info=True)

                # 7. 等待下一轮
                self.logger.info("休眠 %s 秒后继续下一轮决策...", self.config.trader_interval)
                await self._interruptible_sleep(max(1, self.config.trader_interval))

        except asyncio.CancelledError:
            self.logger.info("分层决策主循环被取消，准备退出。")
        except Exception as e:
            self.logger.critical(f"分层决策主循环出现致命错误: {e}", exc_info=True)
            raise
        finally:
            self.running = False
            # 停止数据采集
            if self.data_collector:
                await self.data_collector.stop()

    async def stop(self):
        """停止协调器"""
        self.running = False

        # 停止数据采集服务
        if self.data_collector:
            await self.data_collector.stop()

        # 停止绩效服务
        if self.performance_service:
            await self.performance_service.stop()
            self.logger.info("绩效服务已停止")

    # ------------------------------------------------------------------ #
    # 内部辅助方法
    # ------------------------------------------------------------------ #

    async def _collect_snapshots(self) -> Dict[str, Dict[str, Any]]:
        """收集所有交易对的市场数据快照（直接来自实时采集器）"""
        snapshots = {}

        for symbol in self.symbols:
            snapshot = self.data_collector.get_latest_snapshot(symbol)
            if snapshot:
                snapshots[symbol] = snapshot
            else:
                self.logger.warning("%s 暂无缓存数据，跳过本轮", symbol)

        return snapshots

    async def _make_strategy(
        self,
        portfolio: Portfolio,
        snapshot: Dict[str, Any]
    ) -> Optional[StrategyConfig]:
        """
        生成策略配置

        这里保留一个简化版本,实际逻辑应该由外部传入或在具体实现中覆盖
        """
        from datetime import datetime, timezone
        from decimal import Decimal

        # 获取风险配置
        risk_config = self.config.get_risk_config()
        now = datetime.now(timezone.utc)
        total_value = portfolio.total_value if portfolio.total_value > 0 else Decimal("10000")
        max_trade_value = (total_value * risk_config.max_position_size).quantize(Decimal("0.01"))

        # 简单策略生成逻辑
        return StrategyConfig(
            name="adaptive",
            version="0.1.0",
            description="自适应策略",
            max_position_size=risk_config.max_position_size,
            max_single_trade=max_trade_value,
            max_open_positions=len(self.symbols),
            max_daily_loss=risk_config.max_daily_loss,
            max_drawdown=risk_config.max_drawdown,
            stop_loss_percentage=risk_config.stop_loss_percentage,
            take_profit_percentage=risk_config.take_profit_percentage,
            trading_pairs=self.symbols,
            timeframes=["1h", "4h"],
            updated_at=now,
            reason_for_update=f"策略生成：{now.isoformat()}",
            parameters={}
        )

    async def _execute_signals(
        self,
        signals: Dict[str, Optional[TradingSignal]],
        snapshots: Dict[str, Dict[str, Any]],
        strategy: StrategyConfig,
        portfolio: Portfolio
    ) -> Optional[Portfolio]:
        """执行信号字典 (分层决策模式)，返回最新组合（若有）"""
        if not signals:
            return None

        trade_tasks = []
        for symbol, signal in signals.items():
            if signal is None:
                continue

            if signal.signal_type == SignalType.HOLD:
                continue

            snapshot = snapshots.get(symbol)
            if not snapshot:
                continue

            self.logger.info("%s 收到 %s 信号，准备执行", symbol, signal.signal_type.value)
            task = self.trading_executor.process_trading_signal(
                symbol, signal, strategy, snapshot, portfolio
            )
            trade_tasks.append((symbol, task))

        latest_portfolio = None

        if trade_tasks:
            self.logger.info("🚀 并行执行 %d 个交易信号...", len(trade_tasks))
            tasks_only = [task for _, task in trade_tasks]
            results = await asyncio.gather(*tasks_only, return_exceptions=True)

            for idx, result in enumerate(results):
                if isinstance(result, Exception):
                    symbol = trade_tasks[idx][0] if idx < len(trade_tasks) else "unknown"
                    self.logger.error("%s 执行交易时发生异常: %s", symbol, result, exc_info=result)
                elif result is not None:
                    latest_portfolio = result

        return latest_portfolio

    async def _run_initial_strategist_cycle(self):
        """首次运行战略层分析"""
        import time
        start_time = time.time()

        self.logger.info("\n" + "=" * 60)
        self.logger.info("执行首次战略层分析")
        self.logger.info("=" * 60)

        try:
            # 获取加密市场概览（带超时）
            self.logger.info("[计时] 开始获取加密市场概览...")
            t1 = time.time()

            from src.perception.crypto_overview import CryptoOverviewCollector
            crypto_collector = CryptoOverviewCollector()
            try:
                crypto_overview = await asyncio.wait_for(
                    crypto_collector.get_market_overview(),
                    timeout=15.0  # 15秒超时
                )
            except asyncio.TimeoutError:
                self.logger.warning("加密市场概览获取超时（15秒），跳过")
                crypto_overview = None
            finally:
                await crypto_collector.close()

            t2 = time.time()
            self.logger.info(f"[计时] 加密市场概览获取完成，耗时: {t2-t1:.2f}秒")

            # 战略层LLM分析（带超时）
            self.logger.info("[计时] 开始执行战略层LLM分析...")
            t3 = time.time()
            try:
                await asyncio.wait_for(
                    self.layered_coordinator.run_strategist_cycle(crypto_overview),
                    timeout=120.0  # 2分钟超时
                )
            except asyncio.TimeoutError:
                self.logger.error("战略层LLM分析超时（120秒），将使用默认策略")
                raise
            t4 = time.time()
            self.logger.info(f"[计时] 战略层LLM分析完成，耗时: {t4-t3:.2f}秒")

            total_time = time.time() - start_time
            self.logger.info(f"✅ 战略层分析完成，总耗时: {total_time:.2f}秒")
        except Exception as exc:
            self.logger.error("战略层分析失败: %s", exc, exc_info=True)
            self.logger.warning("将继续运行，但可能影响决策质量")

    async def _run_strategist_cycle(self):
        """定期运行战略层分析"""
        self.logger.info("\n" + "=" * 60)
        self.logger.info("执行战略层分析")
        self.logger.info("=" * 60)

        try:
            from src.perception.crypto_overview import CryptoOverviewCollector
            crypto_collector = CryptoOverviewCollector()
            try:
                crypto_overview = await crypto_collector.get_market_overview()
            finally:
                await crypto_collector.close()

            await self.layered_coordinator.run_strategist_cycle(crypto_overview)
            self.logger.info("✅ 战略层分析完成")
        except Exception as exc:
            self.logger.error("战略层分析失败: %s", exc, exc_info=True)

    async def _interruptible_sleep(self, seconds: float, check_interval: float = 0.1) -> None:
        """
        可中断的 sleep,定期检查 self.running 标志

        Args:
            seconds: 总共要 sleep 的秒数
            check_interval: 检查间隔(秒),默认 0.1 秒检查一次
        """
        elapsed = 0.0
        while elapsed < seconds and self.running:
            sleep_time = min(check_interval, seconds - elapsed)
            await asyncio.sleep(sleep_time)
            elapsed += sleep_time
