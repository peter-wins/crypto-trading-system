"""
Decorators for exchange API calls.

Provides retry logic, error handling, and logging for exchange operations.
"""

import asyncio
import functools
from typing import Callable, Any, Optional, Type
import time

from src.core.logger import get_logger
from src.core.exceptions import (
    ExchangeConnectionError,
    OrderExecutionError,
    RateLimitError,
    InsufficientBalanceError,
)

logger = get_logger(__name__)


def with_retry(
    max_retries: int = 3,
    backoff_factor: float = 1.0,
    exceptions: tuple = (ExchangeConnectionError, Exception),
):
    """
    API调用重试装饰器

    Args:
        max_retries: 最大重试次数
        backoff_factor: 退避因子（每次重试等待时间翻倍）
        exceptions: 需要重试的异常类型

    Example:
        @with_retry(max_retries=3)
        async def fetch_data():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)

                except exceptions as e:
                    last_exception = e

                    if attempt < max_retries:
                        wait_time = backoff_factor * (2 ** attempt)
                        logger.warning(
                            f"{func.__name__} failed (attempt {attempt + 1}/{max_retries + 1}): "
                            f"{str(e)}. Retrying in {wait_time}s..."
                        )
                        await asyncio.sleep(wait_time)
                    else:
                        logger.error(
                            f"{func.__name__} failed after {max_retries + 1} attempts: {str(e)}"
                        )

            # 所有重试都失败
            raise last_exception

        return wrapper
    return decorator


def with_timeout(seconds: float):
    """
    超时装饰器

    Args:
        seconds: 超时时间（秒）

    Example:
        @with_timeout(5.0)
        async def long_running_task():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            try:
                return await asyncio.wait_for(
                    func(*args, **kwargs),
                    timeout=seconds
                )
            except asyncio.TimeoutError:
                logger.error(f"{func.__name__} timed out after {seconds}s")
                raise ExchangeConnectionError(f"Operation timed out after {seconds}s")

        return wrapper
    return decorator


def log_api_call(func: Callable) -> Callable:
    """
    API调用日志装饰器

    记录API调用的参数、返回值和执行时间

    Example:
        @log_api_call
        async def fetch_ticker(symbol: str):
            ...
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs) -> Any:
        start_time = time.time()

        # 提取关键参数用于日志
        func_args = []
        if args and len(args) > 1:  # 跳过self
            func_args = args[1:]

        try:
            result = await func(*args, **kwargs)
            duration = time.time() - start_time

            logger.debug(
                f"API call: {func.__name__}({func_args}, {kwargs}) "
                f"completed in {duration:.2f}s"
            )

            return result

        except Exception as e:
            duration = time.time() - start_time
            logger.error(
                f"API call: {func.__name__}({func_args}, {kwargs}) "
                f"failed after {duration:.2f}s: {str(e)}"
            )
            raise

    return wrapper


def handle_exchange_errors(func: Callable) -> Callable:
    """
    交易所错误处理装饰器

    统一处理交易所API异常，转换为自定义异常

    Example:
        @handle_exchange_errors
        async def create_order():
            ...
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs) -> Any:
        try:
            return await func(*args, **kwargs)

        except Exception as e:
            error_msg = str(e).lower()

            # 网络相关错误
            if any(keyword in error_msg for keyword in [
                'timeout', 'connection', 'network', 'refused'
            ]):
                raise ExchangeConnectionError(f"Network error in {func.__name__}: {str(e)}")

            # 余额不足
            if 'insufficient' in error_msg or 'balance' in error_msg:
                raise OrderExecutionError(f"Insufficient balance: {str(e)}")

            # 订单相关错误
            if 'order' in error_msg:
                raise OrderExecutionError(f"Order error in {func.__name__}: {str(e)}")

            # API限流
            if 'rate' in error_msg or 'limit' in error_msg:
                logger.warning(f"Rate limit hit in {func.__name__}, should wait...")
                raise OrderExecutionError(f"Rate limit exceeded: {str(e)}")

            # 其他交易所错误
            raise OrderExecutionError(f"Exchange error in {func.__name__}: {str(e)}")

    return wrapper


def cached(ttl: int = 60):
    """
    缓存装饰器（简单实现）

    Args:
        ttl: 缓存过期时间（秒）

    Example:
        @cached(ttl=30)
        async def fetch_ticker(symbol: str):
            ...
    """
    cache = {}

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            # 生成缓存key
            cache_key = (func.__name__, args[1:], tuple(sorted(kwargs.items())))

            # 检查缓存
            if cache_key in cache:
                result, timestamp = cache[cache_key]
                if time.time() - timestamp < ttl:
                    logger.debug(f"Cache hit for {func.__name__}")
                    return result

            # 调用函数
            result = await func(*args, **kwargs)

            # 更新缓存
            cache[cache_key] = (result, time.time())

            return result

        # 添加清除缓存方法
        wrapper.clear_cache = lambda: cache.clear()

        return wrapper
    return decorator


# 组合装饰器：常用的API调用装饰器组合
def api_call(
    max_retries: int = 3,
    timeout: float = 30.0,
    log: bool = True,
):
    """
    组合装饰器：重试 + 超时 + 日志 + 错误处理

    Example:
        @api_call(max_retries=3, timeout=10.0)
        async def fetch_balance():
            ...
    """
    def decorator(func: Callable) -> Callable:
        # 按顺序应用装饰器（从内到外）
        wrapped = func

        # 1. 错误处理（最内层）
        wrapped = handle_exchange_errors(wrapped)

        # 2. 日志
        if log:
            wrapped = log_api_call(wrapped)

        # 3. 超时
        wrapped = with_timeout(timeout)(wrapped)

        # 4. 重试（最外层）
        wrapped = with_retry(max_retries=max_retries)(wrapped)

        return wrapped

    return decorator
