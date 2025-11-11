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
from src.perception.market_data import CCXTMarketDataCollector
from src.perception.indicators import PandasIndicatorCalculator
from src.perception.data_collector import MarketDataCollector
from src.perception.symbol_mapper import SymbolMapper
from src.perception.kline_manager import KlineDataManager
from src.perception.kline_cleaner import KlineDataCleaner
from src.perception.market_analyzer import MarketAnalyzer
from src.memory.short_term import RedisShortTermMemory
from src.memory.long_term import QdrantLongTermMemory
from src.execution.order import CCXTOrderExecutor
from src.execution.risk import StandardRiskManager
from src.execution.portfolio import PortfolioManager
from src.execution.trading_executor import TradingExecutor
from src.database.session import get_db_manager, DatabaseManager
from src.perception.http_utils import close_global_http_client


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
        self.kline_manager: Optional[KlineDataManager] = None
        self.kline_cleaner: Optional[KlineDataCleaner] = None

        self.short_term_memory: Optional[RedisShortTermMemory] = None
        self.long_term_memory: Optional[any] = None

        self.order_executor: Optional[CCXTOrderExecutor] = None
        self.risk_manager: Optional[StandardRiskManager] = None
        self.portfolio_manager: Optional[PortfolioManager] = None
        self.trading_executor: Optional[TradingExecutor] = None

        self.db_manager: Optional[DatabaseManager] = None
        self.symbol_mapper: Optional[SymbolMapper] = None

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
        self.logger.info("=" * 60)
        self.logger.info("开始构建交易系统")
        self.logger.info("=" * 60)

        # 2. 初始化数据源和交易对
        await self._setup_data_source()

        # 3. 初始化感知组件
        await self._setup_perception()

        # 4. 初始化内存
        await self._setup_memory()

        # 5. 初始化执行组件
        await self._setup_execution()

        # 6. 初始化数据库
        await self._setup_database()

        # 7. 初始化数据采集服务
        await self._setup_data_collector()

        # 8. 初始化交易执行服务
        await self._setup_trading_executor()

        # 9. 初始化分层决策 (如果启用)
        await self._setup_layered_decision()

        # 10. 创建协调器
        coordinator = self._create_coordinator()

        self.logger.info("=" * 60)
        self.logger.info("✅ 交易系统构建完成")
        self.logger.info("=" * 60)

        return coordinator

    async def _load_config(self):
        """加载配置"""
        self.config = get_config()
        self.logger = get_logger(__name__)
        self.logger.info("✅ 配置加载完成")

    async def _setup_data_source(self):
        """设置数据源和交易对"""
        self.data_source_id = self.config.data_source_exchange or "binance"

        # 根据配置选择交易所ID
        if self.config.binance_futures:
            self.exchange_id = "binanceusdm"  # USDT永续合约使用 binanceusdm
        else:
            self.exchange_id = "binance"  # 现货使用 binance

        # 交易对
        trading_symbols = self.config.get_data_source_symbols()
        if self.config.binance_futures:
            self.symbols = [f"{pair}:USDT" for pair in trading_symbols]
            self.logger.info("USDT 永续合约模式，交易对: %s", self.symbols)
        else:
            self.symbols = trading_symbols
            self.logger.info("现货模式，交易对: %s", self.symbols)

        self.logger.info(f"数据源: {self.data_source_id}, 交易所: {self.exchange_id}")

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

        self.logger.info("✅ 感知组件初始化完成")

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
            self.logger.info("初始化 Qdrant 长期记忆库")
            self.long_term_memory = QdrantLongTermMemory(
                qdrant_url=self.config.qdrant_url,
                openai_api_key=self.config.openai_api_key,
                embedding_model=self.config.openai_embedding_model,
            )
            await self.long_term_memory.initialize()
        else:
            self.logger.info("跳过长期记忆初始化（未配置 OpenAI API Key）")

        self.logger.info("✅ 内存组件初始化完成")

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
        )

        if not self.config.enable_trading:
            self.logger.warning("当前处于纸面交易模式（未启用真实下单）。")
        else:
            # 真实交易模式：启动时强制同步一次获取真实持仓
            try:
                await self.portfolio_manager.get_current_portfolio(force_sync=True)
                self.logger.info("✅ 已连接到交易所并同步持仓")
            except Exception as e:
                self.logger.error(f"无法连接到交易所: {e}")
                self.logger.warning("⚠️  由于交易所连接失败，将回退到纸面交易模式")
                # 回退到纸面交易模式
                self.portfolio_manager.paper_trading = True
                self.portfolio_manager._portfolio_cache = initial_portfolio

        self.logger.info("✅ 执行组件初始化完成")

    async def _setup_database(self):
        """初始化数据库"""
        self.db_manager = get_db_manager(
            database_url=self.config.database_url,
            echo=False
        )
        # get_db_manager() 内部已经调用了 initialize()
        self.logger.info("✅ 数据库初始化完成")

    async def _setup_data_collector(self):
        """初始化数据采集服务"""
        # 获取DAO实例用于保存K线数据
        # 使用新的KlineDataManager替代旧的MarketDataCollector
        # 传入db_manager而不是dao，让每个采集任务创建独立session
        self.kline_manager = KlineDataManager(
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
        self.kline_cleaner = KlineDataCleaner(
            kline_manager=self.kline_manager,
            cleanup_interval=86400,  # 每24小时清理一次
            logger=self.logger,
        )

        self.logger.info("✅ K线数据管理服务初始化完成")

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
        self.logger.info("✅ 交易执行服务初始化完成")

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
                self.logger.info(f"🤖 使用千问模型: {self.config.qwen_model}")
                llm_client = QwenClient(
                    api_key=self.config.qwen_api_key,
                    base_url=self.config.qwen_base_url,
                    model=self.config.qwen_model,
                )
            else:
                self.logger.info(f"🤖 使用DeepSeek模型: {self.config.deepseek_model}")
                llm_client = DeepSeekClient(
                    api_key=self.config.deepseek_api_key,
                    base_url=self.config.deepseek_base_url,
                    model=self.config.deepseek_model,
                )

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

            self.logger.info("✅ 分层决策架构初始化完成")

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
            logger=self.logger,
        )

    async def cleanup(self):
        """清理所有资源"""
        self.logger.info("开始清理资源...")

        if self.data_collector:
            await self.data_collector.stop()

        if self.market_collector:
            await self.market_collector.close()

        if self.short_term_memory:
            await self.short_term_memory.close()

        if self.long_term_memory and hasattr(self.long_term_memory, 'close'):
            await self.long_term_memory.close()

        if self.order_executor:
            await self.order_executor.close()

        if self.portfolio_manager:
            await self.portfolio_manager.close()

        if self.db_manager:
            await self.db_manager.close()

        if self.environment_builder and hasattr(self.environment_builder, 'close'):
            await self.environment_builder.close()

        # 关闭全局 HTTP 客户端
        await close_global_http_client()

        self.logger.info("✅ 资源清理完成")
