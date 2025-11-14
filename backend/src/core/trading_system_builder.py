#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Trading System Builder

交易系统构建器,使用构建器模式初始化所有组件。
将初始化逻辑从 main.py 中分离,使代码更清晰、更易维护。
"""

import logging
from typing import List, Optional, Tuple
from decimal import Decimal

from src.core.config import get_config, Config, RiskConfig
from src.core.logger import get_logger
from src.core.trading_coordinator import TradingCoordinator
from src.services.market_data import CCXTMarketDataCollector
from src.perception.indicators import PandasIndicatorCalculator
from src.services.market_data import MarketDataCollector
from src.perception.symbol_mapper import SymbolMapper
from src.services.kline import KlineManager
from src.services.kline import KlineCleaner
from src.perception.market_analyzer import MarketAnalyzer
from src.memory.short_term import RedisShortTermMemory
from src.memory.long_term import QdrantLongTermMemory
from src.execution.order import CCXTOrderExecutor
from src.execution.risk import StandardRiskManager
from src.execution.portfolio import PortfolioManager
from src.execution.trading_executor import TradingExecutor
from src.services.database import get_db_manager, DatabaseManager
from src.perception.http_utils import close_global_http_client
from src.services.exchange.exchange_service import close_exchange_service
from src.services.account_sync import AccountSyncService
from src.services.exchange import ExchangeService


class TradingSystemBuilder:
    """
    交易系统构建器

    使用构建器模式逐步初始化交易系统的所有组件。
    """

    def __init__(self):
        """初始化构建器"""
        self.config: Optional[Config] = None
        self.logger: Optional[logging.Logger] = None

        # 数据源和交易所
        self.data_source_id: str = ""
        self.exchange_id: str = ""
        self.symbols: List[str] = []

        # 组件
        self.market_collector: Optional[CCXTMarketDataCollector] = None
        self.indicator_calculator: Optional[PandasIndicatorCalculator] = None
        self.market_analyzer: Optional[MarketAnalyzer] = None
        self.data_collector: Optional[MarketDataCollector] = None
        self.kline_manager: Optional[KlineManager] = None
        self.kline_cleaner: Optional[KlineCleaner] = None

        self.short_term_memory: Optional[RedisShortTermMemory] = None
        self.long_term_memory: Optional[any] = None

        self.order_executor: Optional[CCXTOrderExecutor] = None
        self.risk_manager: Optional[StandardRiskManager] = None
        self.portfolio_manager: Optional[PortfolioManager] = None
        self.trading_executor: Optional[TradingExecutor] = None

        self.db_manager: Optional[DatabaseManager] = None
        self.symbol_mapper: Optional[SymbolMapper] = None

        # 账户同步服务
        self.account_sync_service: Optional[AccountSyncService] = None
        self.exchange_service: Optional[ExchangeService] = None

        # 绩效服务
        self.performance_service: Optional[any] = None

        # 分层决策组件
        self.layered_coordinator: Optional[any] = None
        self.environment_builder: Optional[any] = None

    async def build(self) -> TradingCoordinator:
        """
        构建完整的交易系统

        Returns:
            初始化完成的 TradingCoordinator
        """
        # 1. 加载配置 (必须首先执行,因为需要 logger)
        await self._load_config()

        # 打印构建开始信息
        self.logger.info("[系统] 开始构建交易系统组件...")

        # 2. 初始化数据源和交易对
        await self._setup_data_source()

        # 3. 初始化感知组件
        await self._setup_perception()

        # 4. 初始化内存
        await self._setup_memory()

        # 5. 初始化数据库 (必须在执行组件之前初始化)
        await self._setup_database()

        # 6. 初始化执行组件
        await self._setup_execution()

        # 7. 初始化数据采集服务
        await self._setup_data_collector()

        # 8. 初始化交易执行服务
        await self._setup_trading_executor()

        # 9. 初始化账户同步服务
        await self._setup_account_sync()

        # 10. 初始化绩效服务
        await self._setup_performance_service()

        # 11. 初始化分层决策 (如果启用)
        await self._setup_layered_decision()

        # 12. 创建协调器
        coordinator = self._create_coordinator()

        self.logger.info("✓ [系统] 交易系统构建完成")

        return coordinator

    async def _load_config(self):
        """加载配置"""
        self.config = get_config()
        self.logger = get_logger(__name__)
        self.logger.info("✓ [配置] 加载完成")

    async def _setup_data_source(self):
        """设置数据源和交易对"""
        self.data_source_id = self.config.data_source_exchange or "binance"

        # 根据配置选择交易所ID
        if self.config.binance_futures:
            self.exchange_id = "binanceusdm"  # USDT 永续合约
            # 数据源同样切换到期货测试网，确保 AccountSync/DB 使用同一 exchange_id
            self.data_source_id = "binanceusdm"
        else:
            self.exchange_id = "binance"
            self.data_source_id = "binance"

        # 交易对
        trading_symbols = self.config.get_data_source_symbols()
        if self.config.binance_futures:
            self.symbols = [f"{pair}:USDT" for pair in trading_symbols]
            mode = "USDT永续合约"
        else:
            self.symbols = trading_symbols
            mode = "现货"

        self.logger.info(
            f"[交易所] {mode} | 数据源: {self.data_source_id} | 交易所: {self.exchange_id} | 交易对: {self.symbols}"
        )

    async def _setup_perception(self):
        """初始化感知组件"""
        # 数据源配置
        data_source_config = {
            "enableRateLimit": True,
            "options": {"defaultType": "future" if self.config.binance_futures else "spot"},
        }

        if self.data_source_id == "binance" and self.config.binance_testnet:
            data_source_config["urls"] = {
                "api": {
                    "public": "https://testnet.binancefuture.com/fapi/v1"
                    if self.config.binance_futures
                    else "https://testnet.binance.vision/api/v3",
                }
            }

        # 初始化市场数据采集器
        self.market_collector = CCXTMarketDataCollector(
            exchange_id=self.data_source_id,
            config=data_source_config,
        )
        await self.market_collector.initialize()

        # 技术指标计算器
        self.indicator_calculator = PandasIndicatorCalculator()

        # 市场分析器
        self.market_analyzer = MarketAnalyzer(indicator_calculator=self.indicator_calculator)

        # 符号映射器
        self.symbol_mapper = SymbolMapper(
            source_exchange=self.data_source_id,
            target_exchange=self.exchange_id,
        )

        self.logger.info("✓ [感知] 初始化完成")

    async def _setup_memory(self):
        """初始化内存组件"""
        # 短期内存 (Redis)
        self.short_term_memory = RedisShortTermMemory(self.config.redis_url)
        await self.short_term_memory.connect()

        # 长期内存 (Qdrant, 可选)
        if (
            self.config.openai_api_key
            and not self.config.openai_api_key.lower().startswith("your_")
        ):
            self.long_term_memory = QdrantLongTermMemory(
                qdrant_url=self.config.qdrant_url,
                openai_api_key=self.config.openai_api_key,
                embedding_model=self.config.openai_embedding_model,
            )
            await self.long_term_memory.initialize()
        else:
            self.logger.debug("跳过长期记忆初始化（未配置 OpenAI API Key）")

        self.logger.info("✓ [内存] 初始化完成")

    async def _setup_execution(self):
        """初始化执行组件"""
        # 交易所配置
        if self.config.binance_futures:
            # USDT 永续合约配置
            exchange_config = {
                "enableRateLimit": True,
                "testnet": self.config.binance_testnet,
                "options": {
                    "adjustForTimeDifference": True,
                    "defaultType": "future",
                    "defaultMarket": "future",
                    "testnet": self.config.binance_testnet,
                },
            }
        else:
            # 现货配置
            exchange_config = {
                "enableRateLimit": True,
                "testnet": self.config.binance_testnet,
                "options": {
                    "adjustForTimeDifference": True,
                    "defaultType": "spot",
                    "testnet": self.config.binance_testnet,
                },
            }

        # 添加 API Key（如果已配置）
        if self.exchange_id in ["binance", "binanceusdm"]:
            if self.config.binance_api_key and self.config.binance_api_secret:
                exchange_config["apiKey"] = self.config.binance_api_key
                exchange_config["secret"] = self.config.binance_api_secret
            else:
                self.logger.warning("未配置 Binance API Key，将仅能获取公开行情。")

        # 订单执行器
        self.order_executor = CCXTOrderExecutor(
            exchange_id=self.exchange_id,
            config=exchange_config,
            paper_trading=not self.config.enable_trading,
        )

        # 风险管理器
        risk_config = RiskConfig(
            max_position_size=self.config.max_position_size,
            max_daily_loss=self.config.max_daily_loss,
            max_drawdown=self.config.max_drawdown,
            stop_loss_percentage=self.config.stop_loss_percentage,
            take_profit_percentage=self.config.take_profit_percentage,
        )
        self.risk_manager = StandardRiskManager(circuit_breaker_threshold=risk_config.max_drawdown)

        # 投资组合管理器
        initial_portfolio = self._build_initial_portfolio() if not self.config.enable_trading else None
        self.portfolio_manager = PortfolioManager(
            exchange_id=self.exchange_id,
            config=exchange_config,
            paper_trading=not self.config.enable_trading,
            initial_portfolio=initial_portfolio,
            sync_interval_seconds=300,  # 5分钟同步一次，避免频繁API调用
            db_manager=self.db_manager,  # 传递数据库管理器
            # account_sync_service 将在 _setup_account_sync() 后设置
        )

        if not self.config.enable_trading:
            self.logger.warning("[交易] 纸面交易模式（未启用真实下单）")
        else:
            self.logger.info("✓ [交易] 真实交易模式")

    async def _setup_database(self):
        """初始化数据库"""
        self.db_manager = get_db_manager(
            database_url=self.config.database_url,
            echo=False
        )
        # get_db_manager() 内部已经调用了 initialize()
        self.logger.info("✓ [数据库] 初始化完成")

    async def _setup_data_collector(self):
        """初始化数据采集服务"""
        # 获取DAO实例用于保存K线数据
        # 使用新的KlineManager替代旧的MarketDataCollector
        # 传入db_manager而不是dao，让每个采集任务创建独立session
        self.kline_manager = KlineManager(
            symbols=self.symbols,
            market_collector=self.market_collector,
            short_term_memory=self.short_term_memory,
            db_manager=self.db_manager if hasattr(self, 'db_manager') else None,
            logger=self.logger,
        )

        # 保留旧的data_collector用于兼容性（单周期1h采集）
        self.data_collector = MarketDataCollector(
            symbols=self.symbols,
            market_collector=self.market_collector,
            indicator_calculator=self.indicator_calculator,
            short_term_memory=self.short_term_memory,
            collection_interval=self.config.data_collection_interval,
            logger=self.logger,
            dao=None,  # 不需要dao，K线保存由kline_manager统一管理
            save_klines=False,  # 关闭保存，由kline_manager统一管理
        )

        # 初始化清理器
        self.kline_cleaner = KlineCleaner(
            kline_manager=self.kline_manager,
            cleanup_interval=86400,  # 每24小时清理一次
            logger=self.logger,
        )

        self.logger.info("✓ [K线服务] 初始化完成")

    async def _setup_trading_executor(self):
        """初始化交易执行服务"""
        self.trading_executor = TradingExecutor(
            order_executor=self.order_executor,
            risk_manager=self.risk_manager,
            portfolio_manager=self.portfolio_manager,
            short_term_memory=self.short_term_memory,
            db_manager=self.db_manager,
            risk_config=RiskConfig(
                max_position_size=self.config.max_position_size,
                max_daily_loss=self.config.max_daily_loss,
                max_drawdown=self.config.max_drawdown,
                stop_loss_percentage=self.config.stop_loss_percentage,
                take_profit_percentage=self.config.take_profit_percentage,
            ),
            symbol_mapper=self.symbol_mapper,
            enable_trading=self.config.enable_trading,
            logger=self.logger,
        )
        self.logger.info("✓ [交易执行] 初始化完成")

    async def _setup_account_sync(self):
        """初始化账户同步服务"""
        # 只在启用真实交易时才启动账户同步服务
        if not self.config.enable_trading:
            self.logger.info("纸面交易模式下跳过账户同步服务")
            return

        # 检查是否配置了 API Key
        if not (self.config.binance_api_key and self.config.binance_api_secret):
            self.logger.warning("未配置 API Key，跳过账户同步服务")
            return

        try:
            # 初始化 ExchangeService（单例模式，从配置文件自动读取）
            self.exchange_service = ExchangeService()

            # 创建账户同步服务
            self.account_sync_service = AccountSyncService(
                exchange_service=self.exchange_service,
                db_manager=self.db_manager,
                sync_interval=10,  # 每10秒同步一次
                db_exchange_name=self.exchange_id or "binance",
            )

            # 启动同步服务
            await self.account_sync_service.start()

            # 将账户同步服务设置到 PortfolioManager 中
            if self.portfolio_manager:
                self.portfolio_manager.account_sync_service = self.account_sync_service

            self.logger.info("✓ [账户同步] 初始化完成 (间隔: 10秒)")

        except Exception as e:
            self.logger.error(f"[账户同步] 初始化失败: {e}", exc_info=True)
            # 不抛出异常，允许系统在没有账户同步的情况下继续运行
            self.account_sync_service = None

    async def _setup_layered_decision(self):
        """初始化分层决策架构 (可选)"""
        if not self.config.layered_decision_enabled:
            self.logger.info("分层决策架构未启用")
            return

        try:
            from src.decision import DeepSeekClient, LLMStrategist, LLMTrader, ToolRegistry
            from src.decision.layered_coordinator import LayeredDecisionCoordinator
            from src.perception.environment_builder import EnvironmentBuilder
            from src.memory.retrieval import RAGMemoryRetrieval
            from src.decision.tools import MarketDataQueryTool, TechnicalAnalysisTool, MemorySearchTool

            # 根据配置初始化 LLM 客户端
            if self.config.ai_provider == "qwen":
                from src.decision import QwenClient
                llm_client = QwenClient(
                    api_key=self.config.qwen_api_key,
                    base_url=self.config.qwen_base_url,
                    model=self.config.qwen_model,
                )
                model_info = f"千问 {self.config.qwen_model}"
            else:
                llm_client = DeepSeekClient(
                    api_key=self.config.deepseek_api_key,
                    base_url=self.config.deepseek_base_url,
                    model=self.config.deepseek_model,
                )
                model_info = f"DeepSeek {self.config.deepseek_model}"

            # 创建 RAGMemoryRetrieval
            memory_retrieval = RAGMemoryRetrieval(
                self.short_term_memory,
                self.long_term_memory,
            )

            # 初始化工具注册器并注册工具
            tool_registry = ToolRegistry()
            tool_registry.register(MarketDataQueryTool(self.market_collector))
            tool_registry.register(
                TechnicalAnalysisTool(self.market_collector, self.indicator_calculator)
            )
            tool_registry.register(MemorySearchTool(memory_retrieval))

            # 创建 Strategist 和 Trader
            strategist = LLMStrategist(
                llm_client=llm_client,
                memory_retrieval=memory_retrieval,
                tool_registry=tool_registry,
                symbols=self.symbols,
            )

            trader = LLMTrader(
                llm_client=llm_client,
                tool_registry=tool_registry,
                memory_retrieval=memory_retrieval,
            )

            # 环境构建器
            self.environment_builder = EnvironmentBuilder(
                llm_client=llm_client,
                cryptopanic_api_key=self.config.cryptopanic_api_key if hasattr(self.config, 'cryptopanic_api_key') else None,
                enable_news=self.config.enable_news if hasattr(self.config, 'enable_news') else False,
            )

            # 分层决策协调器
            self.layered_coordinator = LayeredDecisionCoordinator(
                strategist=strategist,
                trader=trader,
                environment_builder=self.environment_builder,
                strategist_interval_seconds=self.config.strategist_interval,
                trader_interval_seconds=self.config.trader_interval,
                database_manager=self.db_manager,  # 传入数据库管理器用于保存决策
            )

            self.logger.info(f"✓ [AI决策] 初始化完成 | 模型: {model_info}")

        except Exception as exc:
            self.logger.error("分层决策架构初始化失败: %s", exc, exc_info=True)
            raise

    def _build_initial_portfolio(self):
        """构造纸面交易的初始组合（仅现金）"""
        from datetime import datetime, timezone
        from src.execution.portfolio import Portfolio

        now = datetime.now(timezone.utc)
        cash = Decimal("10000")
        return Portfolio(
            timestamp=int(now.timestamp() * 1000),
            dt=now,
            total_value=cash,
            cash=cash,
            positions=[],
            total_pnl=Decimal("0"),
            daily_pnl=Decimal("0"),
            total_return=Decimal("0"),
        )

    def _create_coordinator(self) -> TradingCoordinator:
        """创建交易协调器"""
        return TradingCoordinator(
            config=self.config,
            data_collector=self.data_collector,
            trading_executor=self.trading_executor,
            portfolio_manager=self.portfolio_manager,
            decision_maker=None,  # 传统模式的决策器
            layered_coordinator=self.layered_coordinator,
            kline_manager=self.kline_manager,
            kline_cleaner=self.kline_cleaner,
            market_analyzer=self.market_analyzer,
            account_sync_service=self.account_sync_service,
            performance_service=self.performance_service,
            logger=self.logger,
        )

    async def cleanup(self):
        """清理所有资源"""
        self.logger.info("开始清理资源...")

        # 停止账户同步服务
        if self.account_sync_service:
            try:
                await self.account_sync_service.stop()
            except Exception as exc:
                self.logger.warning("停止 account_sync_service 失败: %s", exc)
            finally:
                self.account_sync_service = None

        # 关闭 ExchangeService
        if self.exchange_service:
            try:
                await self.exchange_service.close()
            except Exception as exc:
                self.logger.warning("关闭 exchange_service 失败: %s", exc)
            finally:
                self.exchange_service = None

        if self.data_collector:
            try:
                await self.data_collector.stop()
            except Exception as exc:
                self.logger.warning("停止 data_collector 失败: %s", exc)

        if self.kline_manager:
            try:
                await self.kline_manager.stop()
            except Exception as exc:
                self.logger.warning("停止 kline_manager 失败: %s", exc)
            finally:
                self.kline_manager = None

        if self.kline_cleaner:
            try:
                await self.kline_cleaner.stop()
            except Exception as exc:
                self.logger.warning("停止 kline_cleaner 失败: %s", exc)
            finally:
                self.kline_cleaner = None

        if self.market_collector:
            try:
                await self.market_collector.close()
            except Exception as exc:
                self.logger.warning("关闭 market_collector 失败: %s", exc)
            finally:
                self.market_collector = None

        if self.short_term_memory:
            await self.short_term_memory.close()

        if self.long_term_memory and hasattr(self.long_term_memory, 'close'):
            await self.long_term_memory.close()

        if self.order_executor:
            try:
                await self.order_executor.close()
            except Exception as exc:
                self.logger.warning("关闭 order_executor 失败: %s", exc)
            finally:
                self.order_executor = None

        if self.portfolio_manager:
            try:
                await self.portfolio_manager.close()
            except Exception as exc:
                self.logger.warning("关闭 portfolio_manager 失败: %s", exc)
            finally:
                self.portfolio_manager = None

        if self.db_manager:
            try:
                await self.db_manager.close()
            except Exception as exc:
                self.logger.warning("关闭数据库失败: %s", exc)
            finally:
                self.db_manager = None

        if self.environment_builder and hasattr(self.environment_builder, 'close'):
            await self.environment_builder.close()

        # 关闭全局 HTTP 客户端
        await close_global_http_client()
        await close_exchange_service()

        self.logger.info("✅ 资源清理完成")

    async def _setup_performance_service(self):
        """初始化绩效服务"""
        try:
            from src.services.performance_service import PerformanceService
            
            # 创建绩效服务
            self.performance_service = PerformanceService(
                db_manager=self.db_manager,
                exchange_name=self.exchange_id or "binanceusdm"
            )

            self.logger.info("✓ [绩效服务] 初始化完成 (每日凌晨00:10自动计算)")

        except Exception as e:
            self.logger.error(f"[绩效服务] 初始化失败: {e}", exc_info=True)
            # 不抛出异常，允许系统在没有绩效服务的情况下继续运行
