"""
Services module - External service integrations.

Contains:
- Exchange service: Unified exchange API access
- LLM service: Large language model integrations (future)
- Data service: External data providers (future)
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
]
