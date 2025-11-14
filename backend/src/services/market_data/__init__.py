"""
Market Data Service - Unified market data collection.

Provides centralized market data collection with:
- CCXT-based data collection
- Background data collection service
- Indicator calculation integration
- Redis caching
"""

from src.services.market_data.ccxt_collector import CCXTMarketDataCollector
from src.services.market_data.collector_service import MarketDataCollector

__all__ = [
    'CCXTMarketDataCollector',
    'MarketDataCollector',
]
