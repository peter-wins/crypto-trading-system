"""
感知模块

本模块负责市场数据采集、技术指标计算、数据验证和市场环境数据采集。

注意：CCXTMarketDataCollector 和 MarketDataCollector 已迁移到 src.services.market_data
如需使用请直接从 src.services.market_data 导入
"""

# Import K-line services from new location
from src.services.kline import (
    KlineManager,
    KlineCleaner,
    TimeframeConfig,
    DataFetchStrategy,
    RateLimitConfig,
    DEFAULT_FETCH_STRATEGY,
    DEFAULT_RATE_LIMIT,
)
# For backward compatibility, create KlineConfig alias
KlineConfig = TimeframeConfig
from .indicators import PandasIndicatorCalculator
from .validator import MarketDataValidator
from .environment_builder import EnvironmentBuilder
from .sentiment import SentimentCollector
from .macro import MacroCollector
from .stocks import StockCollector
from .crypto_overview import CryptoOverviewCollector
from .news import NewsCollector

__all__ = [
    # Market data collectors moved to src.services.market_data:
    # "CCXTMarketDataCollector", "MarketDataCollector",
    "PandasIndicatorCalculator",
    "MarketDataValidator",
    "EnvironmentBuilder",
    "SentimentCollector",
    "MacroCollector",
    "StockCollector",
    "CryptoOverviewCollector",
    "NewsCollector",
    "KlineManager",
    "KlineCleaner",
    "KlineConfig",
]
