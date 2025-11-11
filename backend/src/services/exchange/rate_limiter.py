"""
Rate limiter for exchange API calls.

Implements token bucket algorithm to prevent hitting exchange rate limits.
"""

import asyncio
import time
from typing import Dict, Optional
from collections import deque

from src.core.logger import get_logger

logger = get_logger(__name__)


class RateLimiter:
    """
    Token bucket rate limiter.

    按照交易所的限流规则，限制API调用频率。
    """

    def __init__(
        self,
        requests_per_second: float = 10.0,
        burst_size: Optional[int] = None,
    ):
        """
        初始化限流器

        Args:
            requests_per_second: 每秒允许的请求数
            burst_size: 突发请求容量（默认为每秒请求数的2倍）
        """
        self.requests_per_second = requests_per_second
        self.burst_size = burst_size or int(requests_per_second * 2)

        # Token bucket
        self.tokens = float(self.burst_size)
        self.last_update = time.time()

        # 统计信息
        self.total_requests = 0
        self.total_waits = 0
        self.total_wait_time = 0.0

        # 请求历史（用于动态调整）
        self.request_history: deque = deque(maxlen=100)

        # 锁，确保线程安全
        self._lock = asyncio.Lock()

        logger.info(
            f"RateLimiter initialized: {requests_per_second} req/s, "
            f"burst={self.burst_size}"
        )

    async def acquire(self, tokens: int = 1) -> None:
        """
        获取令牌，如果不够则等待

        Args:
            tokens: 需要的令牌数（默认1）
        """
        async with self._lock:
            # 更新令牌桶
            now = time.time()
            elapsed = now - self.last_update
            self.tokens = min(
                self.burst_size,
                self.tokens + elapsed * self.requests_per_second
            )
            self.last_update = now

            # 如果令牌不足，计算等待时间
            if self.tokens < tokens:
                wait_time = (tokens - self.tokens) / self.requests_per_second
                self.total_waits += 1
                self.total_wait_time += wait_time

                logger.debug(
                    f"Rate limit: waiting {wait_time:.2f}s "
                    f"(tokens: {self.tokens:.2f}/{self.burst_size})"
                )

                await asyncio.sleep(wait_time)

                # 重新更新令牌
                now = time.time()
                elapsed = now - self.last_update
                self.tokens = min(
                    self.burst_size,
                    self.tokens + elapsed * self.requests_per_second
                )
                self.last_update = now

            # 消耗令牌
            self.tokens -= tokens
            self.total_requests += 1
            self.request_history.append(now)

    def get_stats(self) -> Dict[str, float]:
        """获取限流统计信息"""
        avg_wait = self.total_wait_time / max(1, self.total_waits)

        # 计算最近1分钟的请求速率
        now = time.time()
        recent_requests = sum(
            1 for t in self.request_history
            if now - t < 60
        )
        recent_rate = recent_requests / 60.0

        return {
            "total_requests": self.total_requests,
            "total_waits": self.total_waits,
            "avg_wait_time": avg_wait,
            "current_tokens": self.tokens,
            "recent_rate_per_second": recent_rate,
        }

    def reset(self) -> None:
        """重置限流器"""
        self.tokens = float(self.burst_size)
        self.last_update = time.time()
        self.total_requests = 0
        self.total_waits = 0
        self.total_wait_time = 0.0
        self.request_history.clear()
        logger.info("Rate limiter reset")


class ExchangeRateLimiters:
    """
    管理不同交易所的限流器

    不同交易所有不同的限流规则：
    - Binance: 1200 requests/minute (weight-based)
    - OKX: 300 requests/second
    - Bybit: 120 requests/minute
    """

    EXCHANGE_LIMITS = {
        "binance": 20.0,  # 每秒20个请求 = 1200/60
        "okx": 300.0,
        "bybit": 2.0,  # 每秒2个请求 = 120/60
        "default": 10.0,
    }

    def __init__(self):
        self._limiters: Dict[str, RateLimiter] = {}
        logger.info("ExchangeRateLimiters initialized")

    def get_limiter(self, exchange_name: str = "binance") -> RateLimiter:
        """
        获取指定交易所的限流器

        Args:
            exchange_name: 交易所名称

        Returns:
            RateLimiter实例
        """
        if exchange_name not in self._limiters:
            rate = self.EXCHANGE_LIMITS.get(
                exchange_name.lower(),
                self.EXCHANGE_LIMITS["default"]
            )
            self._limiters[exchange_name] = RateLimiter(
                requests_per_second=rate
            )
            logger.info(f"Created rate limiter for {exchange_name}: {rate} req/s")

        return self._limiters[exchange_name]

    def get_all_stats(self) -> Dict[str, Dict]:
        """获取所有限流器的统计信息"""
        return {
            name: limiter.get_stats()
            for name, limiter in self._limiters.items()
        }


# 全局限流器实例（单例）
_global_rate_limiters: Optional[ExchangeRateLimiters] = None


def get_rate_limiters() -> ExchangeRateLimiters:
    """获取全局限流器实例"""
    global _global_rate_limiters
    if _global_rate_limiters is None:
        _global_rate_limiters = ExchangeRateLimiters()
    return _global_rate_limiters
