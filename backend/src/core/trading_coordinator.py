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
from src.perception.data_collector import MarketDataCollector
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
        kline_manager: Optional[Any] = None,  # KlineDataManager
        kline_cleaner: Optional[Any] = None,  # KlineDataCleaner
        market_analyzer: Optional[Any] = None,  # MarketAnalyzer
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
            kline_manager: K线数据管理器 (多周期采集)
            kline_cleaner: K线数据清理器
            market_analyzer: 市场分析器 (技术指标→简洁摘要)
            logger: 日志记录器
        """
        self.config = config
        self.data_collector = data_collector
        self.trading_executor = trading_executor
        self.portfolio_manager = portfolio_manager
        self.decision_maker = decision_maker
        self.layered_coordinator = layered_coordinator
        self.kline_manager = kline_manager
        self.kline_cleaner = kline_cleaner
        self.market_analyzer = market_analyzer
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
            self.logger.info("启动分层决策主循环")
            self.logger.info("=" * 60)

            if not self.config.enable_trading:
                self.logger.warning("当前处于纸面交易模式（未启用真实下单）。")

            # 启动数据采集服务
            await self.data_collector.start()

            # 启动多周期K线数据管理器
            if self.kline_manager:
                await self.kline_manager.start()
                self.logger.info("✅ K线数据管理器已启动")

            # 启动K线数据清理任务
            if self.kline_cleaner:
                await self.kline_cleaner.start()
                self.logger.info("✅ K线数据清理任务已启动")

            # 首次运行战略层分析
            await self._run_initial_strategist_cycle()

            # 战术层主循环
            trader_cycles = 0
            strategist_interval_cycles = self.config.strategist_interval // self.config.trader_interval

            while self.running:
                trader_cycles += 1

                # 定期运行战略层
                if trader_cycles % strategist_interval_cycles == 0:
                    await self._run_strategist_cycle()
                    trader_cycles = 0

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

                # 6. 执行完成后，重新获取最新持仓并保存快照
                try:
                    if latest_portfolio:
                        portfolio_after = latest_portfolio
                        self.logger.info("📸 使用执行结果中的最新持仓状态")
                    else:
                        self.logger.info("📸 重新获取最新持仓状态...")
                        portfolio_after = await self.portfolio_manager.get_current_portfolio()

                    # 保存执行后的持仓快照
                    if self.layered_coordinator:
                        await self.layered_coordinator._save_snapshots(portfolio_after)
                        self.logger.info("✅ 执行后快照已保存")
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

        # 停止K线数据管理器
        if self.kline_manager:
            await self.kline_manager.stop()
            self.logger.info("K线数据管理器已停止")

        # 停止清理任务
        if self.kline_cleaner:
            await self.kline_cleaner.stop()
            self.logger.info("K线数据清理任务已停止")

    # ------------------------------------------------------------------ #
    # 内部辅助方法
    # ------------------------------------------------------------------ #

    async def _collect_snapshots(self) -> Dict[str, Dict[str, Any]]:
        """
        收集所有交易对的市场数据快照

        优先使用kline_manager+market_analyzer生成简洁的市场摘要,
        如果不可用则回退到data_collector的原始指标
        """
        snapshots = {}

        # 临时禁用market_analyzer,回退到旧格式
        # TODO: 等market_analyzer修复后再启用
        if False and self.kline_manager and self.market_analyzer:
            for symbol in self.symbols:
                try:
                    # 1. 获取实时最新价格(从data_collector)
                    old_snapshot = self.data_collector.get_latest_snapshot(symbol)
                    if not old_snapshot or "latest_price" not in old_snapshot:
                        self.logger.warning("%s 无法获取实时价格，跳过本轮", symbol)
                        continue

                    latest_price = old_snapshot["latest_price"]

                    # 2. 获取1小时K线数据用于技术分析
                    klines = await self.kline_manager.get_klines(symbol, "1h", limit=100)
                    if not klines or len(klines) < 50:
                        self.logger.warning("%s K线数据不足，跳过本轮", symbol)
                        continue

                    # 3. 使用market_analyzer生成市场摘要
                    market_summary = self.market_analyzer.analyze(symbol, "1h", klines)

                    # 4. 构建snapshot,使用实时价格+技术分析摘要
                    snapshot = {
                        "symbol": symbol,
                        "latest_price": latest_price,  # 使用实时价格,不是K线的收盘价
                        "market_summary": market_summary.to_prompt(),  # 简洁的文本摘要
                    }
                    snapshots[symbol] = snapshot

                except Exception as e:
                    self.logger.warning("%s 生成市场摘要失败: %s，尝试使用原始指标", symbol, e)
                    # 回退到原始方式
                    snapshot = self.data_collector.get_latest_snapshot(symbol)
                    if snapshot:
                        snapshots[symbol] = snapshot
        else:
            # 回退到原始data_collector方式
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
        self.logger.info("\n" + "=" * 60)
        self.logger.info("执行首次战略层分析")
        self.logger.info("=" * 60)

        try:
            # 获取加密市场概览
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
