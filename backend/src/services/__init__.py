"""
Services module - External service integrations.

Contains:
- Exchange service: Unified exchange API access
- LLM service: Large language model integrations
- Market data service: Market data collection
- K-line service: K-line data management
- Database service: Data persistence
- Account sync service: Account synchronization with exchange
"""

from src.services.exchange import (
    ExchangeService,
    get_exchange_service,
    RateLimiter,
    get_rate_limiters,
    with_retry,
    with_timeout,
    log_api_call,
    handle_exchange_errors,
    api_call,
)

from src.services.llm import (
    DeepSeekClient,
    QwenClient,
    OpenAIClient,
    Message,
    ToolCall,
    LLMResponse,
)

from src.services.market_data import (
    CCXTMarketDataCollector,
    MarketDataCollector,
)

from src.services.kline import (
    KlineManager,
    KlineCleaner,
    TimeframeConfig,
    DataFetchStrategy,
    RateLimitConfig,
)

from src.services.database import (
    TradingDAO,
    DatabaseManager,
    DatabaseSession,
    get_db_manager,
    get_session_factory,
)

from src.services.account_sync import (
    AccountSyncService,
    AccountSnapshot,
    PositionChange,
)

from src.services.performance_service import (
    PerformanceService,
)

__all__ = [
    # Exchange service
    'ExchangeService',
    'get_exchange_service',

    # Rate limiting
    'RateLimiter',
    'get_rate_limiters',

    # Decorators
    'with_retry',
    'with_timeout',
    'log_api_call',
    'handle_exchange_errors',
    'api_call',

    # LLM service
    'DeepSeekClient',
    'QwenClient',
    'OpenAIClient',
    'Message',
    'ToolCall',
    'LLMResponse',

    # Market data service
    'CCXTMarketDataCollector',
    'MarketDataCollector',

    # K-line service
    'KlineManager',
    'KlineCleaner',
    'TimeframeConfig',
    'DataFetchStrategy',
    'RateLimitConfig',

    # Database service
    'TradingDAO',
    'DatabaseManager',
    'DatabaseSession',
    'get_db_manager',
    'get_session_factory',

    # Account sync service
    'AccountSyncService',
    'AccountSnapshot',
    'PositionChange',

    # Performance service
    'PerformanceService',
]
