"""
短期记忆模块

本模块实现基于Redis的短期记忆功能，用于存储临时上下文信息。
"""

from __future__ import annotations

import json
from typing import Any, Optional
import redis.asyncio as redis

from src.core.logger import get_logger
from src.core.exceptions import TradingSystemError
from src.models.memory import MarketContext, TradingContext


logger = get_logger(__name__)


class RedisShortTermMemory:
    """基于Redis的短期记忆"""

    # Key命名规范
    MARKET_CONTEXT_PREFIX = "market:context:"
    TRADING_CONTEXT_KEY = "trading:context"
    TRADE_ACTION_PREFIX = "trade:action:"
    MARKET_PRICES_PREFIX = "market:prices:"
    INDICATORS_PREFIX = "indicators:"

    # 默认TTL（秒）
    DEFAULT_TTL = 300  # 5分钟
    MARKET_CONTEXT_TTL = 300  # 5分钟
    TRADING_CONTEXT_TTL = 3600  # 1小时
    PRICES_TTL = 3600  # 1小时
    INDICATORS_TTL = 300  # 5分钟
    TRADE_ACTION_TTL = 900  # 15分钟

    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        """
        初始化Redis短期记忆

        Args:
            redis_url: Redis连接URL
        """
        self.redis_url = redis_url
        self.redis: Optional[redis.Redis] = None
        self.logger = logger

    async def connect(self) -> None:
        """连接到Redis"""
        try:
            self.redis = await redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True
            )
            # 测试连接
            await self.redis.ping()
            self.logger.info("Connected to Redis successfully")
        except Exception as e:
            raise TradingSystemError(
                message="Failed to connect to Redis",
                details={"redis_url": self.redis_url},
                original_exception=e
            )

    async def close(self) -> None:
        """关闭Redis连接"""
        if self.redis:
            await self.redis.aclose()
            self.logger.info("Closed Redis connection")

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None
    ) -> bool:
        """
        设置数据

        Args:
            key: 键
            value: 值（将被序列化为JSON）
            ttl: 过期时间（秒），None表示不过期

        Returns:
            是否成功
        """
        try:
            if not self.redis:
                await self.connect()

            # 序列化值
            if isinstance(value, (dict, list)):
                serialized_value = json.dumps(value)
            elif hasattr(value, "model_dump_json"):
                # Pydantic模型
                serialized_value = value.model_dump_json()
            else:
                serialized_value = str(value)

            # 设置值
            if ttl:
                await self.redis.setex(key, ttl, serialized_value)
            else:
                await self.redis.set(key, serialized_value)

            return True
        except Exception as e:
            self.logger.error(f"Failed to set key {key}: {e}")
            return False

    async def get(self, key: str) -> Optional[Any]:
        """
        获取数据

        Args:
            key: 键

        Returns:
            值（自动反序列化），不存在返回None
        """
        try:
            if not self.redis:
                await self.connect()

            value = await self.redis.get(key)
            if value is None:
                return None

            # 尝试反序列化JSON
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        except Exception as e:
            self.logger.error(f"Failed to get key {key}: {e}")
            return None

    async def delete(self, key: str) -> bool:
        """
        删除数据

        Args:
            key: 键

        Returns:
            是否成功
        """
        try:
            if not self.redis:
                await self.connect()

            result = await self.redis.delete(key)
            return result > 0
        except Exception as e:
            self.logger.error(f"Failed to delete key {key}: {e}")
            return False

    async def exists(self, key: str) -> bool:
        """
        检查键是否存在

        Args:
            key: 键

        Returns:
            是否存在
        """
        try:
            if not self.redis:
                await self.connect()

            result = await self.redis.exists(key)
            return result > 0
        except Exception as e:
            self.logger.error(f"Failed to check key existence {key}: {e}")
            return False

    async def get_market_context(
        self,
        symbol: str
    ) -> Optional[MarketContext]:
        """
        获取市场上下文

        Args:
            symbol: 交易对符号

        Returns:
            MarketContext对象，不存在返回None
        """
        try:
            key = f"{self.MARKET_CONTEXT_PREFIX}{symbol}"
            data = await self.get(key)

            if data is None:
                return None

            return MarketContext(**data)
        except Exception as e:
            self.logger.error(f"Failed to get market context for {symbol}: {e}")
            return None

    async def update_market_context(
        self,
        symbol: str,
        context: MarketContext
    ) -> bool:
        """
        更新市场上下文

        Args:
            symbol: 交易对符号
            context: MarketContext对象

        Returns:
            是否成功
        """
        try:
            key = f"{self.MARKET_CONTEXT_PREFIX}{symbol}"
            return await self.set(key, context, ttl=self.MARKET_CONTEXT_TTL)
        except Exception as e:
            self.logger.error(f"Failed to update market context for {symbol}: {e}")
            return False

    async def get_trading_context(self) -> Optional[TradingContext]:
        """
        获取交易上下文

        Returns:
            TradingContext对象，不存在返回None
        """
        try:
            data = await self.get(self.TRADING_CONTEXT_KEY)

            if data is None:
                return None

            return TradingContext(**data)
        except Exception as e:
            self.logger.error(f"Failed to get trading context: {e}")
            return None

    async def update_trading_context(
        self,
        context: TradingContext
    ) -> bool:
        """
        更新交易上下文

        Args:
            context: TradingContext对象

        Returns:
            是否成功
        """
        try:
            return await self.set(
                self.TRADING_CONTEXT_KEY,
                context,
                ttl=self.TRADING_CONTEXT_TTL
            )
        except Exception as e:
            self.logger.error(f"Failed to update trading context: {e}")
            return False

    async def get_last_trade_action(self, symbol: str) -> Optional[dict[str, Any]]:
        """读取最近一次交易动作，用于避免重复执行同一策略。"""
        try:
            key = f"{self.TRADE_ACTION_PREFIX}{symbol}"
            data = await self.get(key)
            if data is None:
                return None
            return data
        except Exception as e:
            self.logger.error(f"Failed to get last trade action for {symbol}: {e}")
            return None

    async def set_last_trade_action(
        self,
        symbol: str,
        action: dict[str, Any],
        *,
        ttl: Optional[int] = None,
    ) -> bool:
        """记录最新交易动作。"""
        try:
            key = f"{self.TRADE_ACTION_PREFIX}{symbol}"
            return await self.set(
                key,
                action,
                ttl=ttl or self.TRADE_ACTION_TTL,
            )
        except Exception as e:
            self.logger.error(f"Failed to set last trade action for {symbol}: {e}")
            return False

    async def get_keys_by_pattern(self, pattern: str) -> list[str]:
        """
        根据模式获取键列表

        Args:
            pattern: Redis键模式，如 "market:context:*"

        Returns:
            键列表
        """
        try:
            if not self.redis:
                await self.connect()

            keys = []
            async for key in self.redis.scan_iter(match=pattern):
                keys.append(key)
            return keys
        except Exception as e:
            self.logger.error(f"Failed to scan keys with pattern {pattern}: {e}")
            return []

    async def clear_all(self) -> bool:
        """
        清空所有数据（谨慎使用！）

        Returns:
            是否成功
        """
        try:
            if not self.redis:
                await self.connect()

            await self.redis.flushdb()
            self.logger.warning("Cleared all Redis data")
            return True
        except Exception as e:
            self.logger.error(f"Failed to clear Redis: {e}")
            return False

    async def get_ttl(self, key: str) -> int:
        """
        获取键的剩余TTL

        Args:
            key: 键

        Returns:
            剩余秒数，-1表示没有过期时间，-2表示键不存在
        """
        try:
            if not self.redis:
                await self.connect()

            return await self.redis.ttl(key)
        except Exception as e:
            self.logger.error(f"Failed to get TTL for key {key}: {e}")
            return -2

    async def set_many(
        self,
        data: dict[str, Any],
        ttl: Optional[int] = None
    ) -> bool:
        """
        批量设置数据

        Args:
            data: 键值对字典
            ttl: 过期时间（秒）

        Returns:
            是否成功
        """
        try:
            if not self.redis:
                await self.connect()

            # 使用pipeline批量操作
            async with self.redis.pipeline() as pipe:
                for key, value in data.items():
                    if isinstance(value, (dict, list)):
                        serialized_value = json.dumps(value)
                    elif hasattr(value, "model_dump_json"):
                        serialized_value = value.model_dump_json()
                    else:
                        serialized_value = str(value)

                    if ttl:
                        pipe.setex(key, ttl, serialized_value)
                    else:
                        pipe.set(key, serialized_value)

                await pipe.execute()

            return True
        except Exception as e:
            self.logger.error(f"Failed to set many keys: {e}")
            return False

    async def get_many(self, keys: list[str]) -> dict[str, Any]:
        """
        批量获取数据

        Args:
            keys: 键列表

        Returns:
            键值对字典
        """
        try:
            if not self.redis:
                await self.connect()

            values = await self.redis.mget(keys)

            result = {}
            for key, value in zip(keys, values):
                if value is not None:
                    try:
                        result[key] = json.loads(value)
                    except json.JSONDecodeError:
                        result[key] = value

            return result
        except Exception as e:
            self.logger.error(f"Failed to get many keys: {e}")
            return {}
