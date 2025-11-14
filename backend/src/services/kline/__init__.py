"""
K-line Service - K线数据管理服务.

Provides centralized K-line data management with:
- K-line data collection
- Data cleaning and validation
- Configuration management
"""

from src.services.kline.kline_service import KlineDataManager as KlineManager
from src.services.kline.cleaner import KlineDataCleaner as KlineCleaner
# Re-export config classes and constants
from src.services.kline.config import (
    TimeframeConfig,
    DataFetchStrategy,
    RateLimitConfig,
    DEFAULT_FETCH_STRATEGY,
    DEFAULT_RATE_LIMIT,
)

__all__ = [
    'KlineManager',
    'KlineCleaner',
    'TimeframeConfig',
    'DataFetchStrategy',
    'RateLimitConfig',
    'DEFAULT_FETCH_STRATEGY',
    'DEFAULT_RATE_LIMIT',
]
