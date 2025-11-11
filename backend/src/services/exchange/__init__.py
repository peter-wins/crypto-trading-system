"""
Exchange module - Unified exchange service.

Provides centralized exchange API access with:
- Rate limiting
- Retry logic
- Error handling
- Connection pooling
- Logging
"""

from src.services.exchange.exchange_service import ExchangeService, get_exchange_service
from src.services.exchange.rate_limiter import RateLimiter, get_rate_limiters
from src.services.exchange.decorators import (
    with_retry,
    with_timeout,
    log_api_call,
    handle_exchange_errors,
    api_call,
)

__all__ = [
    # Main service
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
]
