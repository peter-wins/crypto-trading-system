"""
HTTP Utilities for Perception Layer

提供带有延迟、重试和缓存的 HTTP 请求工具，避免触发 API 频率限制
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from functools import wraps

import aiohttp

from src.core.logger import get_logger

logger = get_logger(__name__)


class CachedHTTPClient:
    """
    带缓存、延迟和重试机制的 HTTP 客户端

    Features:
    - 内存缓存（避免重复请求）
    - 请求延迟（避免触发频率限制）
    - 指数退避重试（处理临时失败）
    - 自动清理过期缓存
    """

    def __init__(
        self,
        cache_ttl_seconds: int = 300,  # 缓存 5 分钟
        request_delay_seconds: float = 0.5,  # 每次请求延迟 0.5 秒
        max_retries: int = 3,  # 最多重试 3 次
        retry_backoff_factor: float = 2.0,  # 重试延迟指数因子
    ):
        self.cache_ttl = timedelta(seconds=cache_ttl_seconds)
        self.request_delay = request_delay_seconds
        self.max_retries = max_retries
        self.retry_backoff_factor = retry_backoff_factor

        self.session: Optional[aiohttp.ClientSession] = None
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._last_request_time: Optional[datetime] = None
        self._request_lock = asyncio.Lock()  # 确保串行请求

    async def _ensure_session(self):
        """确保 HTTP session 存在"""
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=15)
            self.session = aiohttp.ClientSession(timeout=timeout)

    async def close(self):
        """关闭 HTTP session 并清理缓存"""
        if self.session and not self.session.closed:
            await self.session.close()
        self._cache.clear()

    def _get_cache_key(self, url: str, params: Optional[Dict] = None) -> str:
        """生成缓存 key"""
        if params:
            params_str = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
            return f"{url}?{params_str}"
        return url

    def _is_cache_valid(self, cache_entry: Dict) -> bool:
        """检查缓存是否有效"""
        if "timestamp" not in cache_entry or "data" not in cache_entry:
            return False

        cached_at = cache_entry["timestamp"]
        now = datetime.now(timezone.utc)

        return (now - cached_at) < self.cache_ttl

    def _cleanup_expired_cache(self):
        """清理过期缓存"""
        now = datetime.now(timezone.utc)
        expired_keys = [
            key for key, entry in self._cache.items()
            if (now - entry.get("timestamp", now)) >= self.cache_ttl
        ]

        for key in expired_keys:
            del self._cache[key]

        if expired_keys:
            logger.debug(f"清理了 {len(expired_keys)} 个过期缓存")

    async def _apply_rate_limit(self):
        """应用请求延迟（避免触发频率限制）"""
        async with self._request_lock:
            if self._last_request_time is not None:
                elapsed = (datetime.now(timezone.utc) - self._last_request_time).total_seconds()
                delay_needed = self.request_delay - elapsed

                if delay_needed > 0:
                    logger.debug(f"等待 {delay_needed:.2f} 秒以避免触发频率限制")
                    await asyncio.sleep(delay_needed)

            self._last_request_time = datetime.now(timezone.utc)

    async def get_json(
        self,
        url: str,
        params: Optional[Dict] = None,
        headers: Optional[Dict] = None,
        use_cache: bool = True,
    ) -> Optional[Dict]:
        """
        发送 GET 请求并返回 JSON 数据

        Args:
            url: 请求 URL
            params: 查询参数
            headers: 请求头
            use_cache: 是否使用缓存

        Returns:
            JSON 数据字典，失败返回 None
        """
        await self._ensure_session()

        # 检查缓存
        cache_key = self._get_cache_key(url, params)
        if use_cache and cache_key in self._cache:
            cache_entry = self._cache[cache_key]
            if self._is_cache_valid(cache_entry):
                logger.debug(f"使用缓存数据: {cache_key}")
                return cache_entry["data"]

        # 清理过期缓存
        self._cleanup_expired_cache()

        # 应用请求延迟
        await self._apply_rate_limit()

        # 重试机制
        last_error = None
        for attempt in range(self.max_retries):
            try:
                async with self.session.get(url, params=params, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()

                        # 缓存成功的响应
                        if use_cache:
                            self._cache[cache_key] = {
                                "timestamp": datetime.now(timezone.utc),
                                "data": data,
                            }

                        if attempt > 0:
                            logger.info(f"重试第 {attempt} 次成功: {url}")

                        return data

                    elif response.status == 429:
                        # 频率限制，需要更长的延迟
                        wait_time = self.retry_backoff_factor ** attempt
                        logger.warning(
                            f"HTTP 429 频率限制，等待 {wait_time:.1f} 秒后重试 "
                            f"(尝试 {attempt + 1}/{self.max_retries})"
                        )
                        await asyncio.sleep(wait_time)
                        last_error = f"HTTP {response.status}"

                    else:
                        logger.warning(f"HTTP {response.status}: {url}")
                        last_error = f"HTTP {response.status}"
                        break  # 非 429 错误不重试

            except asyncio.TimeoutError:
                wait_time = self.retry_backoff_factor ** attempt * 0.5
                logger.warning(
                    f"请求超时，等待 {wait_time:.1f} 秒后重试 "
                    f"(尝试 {attempt + 1}/{self.max_retries}): {url}"
                )
                await asyncio.sleep(wait_time)
                last_error = "Timeout"

            except Exception as e:
                logger.error(f"请求异常: {e}")
                last_error = str(e)
                break  # 其他异常不重试

        # 所有重试都失败了
        logger.error(f"请求最终失败 ({last_error}): {url}")
        return None

    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        now = datetime.now(timezone.utc)
        valid_count = sum(
            1 for entry in self._cache.values()
            if (now - entry.get("timestamp", now)) < self.cache_ttl
        )

        return {
            "total_cached": len(self._cache),
            "valid_cached": valid_count,
            "expired_cached": len(self._cache) - valid_count,
        }


# 全局单例实例（供所有采集器共享）
_global_http_client: Optional[CachedHTTPClient] = None


def get_http_client() -> CachedHTTPClient:
    """获取全局 HTTP 客户端单例"""
    global _global_http_client
    if _global_http_client is None:
        _global_http_client = CachedHTTPClient(
            cache_ttl_seconds=300,  # 5 分钟缓存
            request_delay_seconds=0.6,  # 请求间隔 0.6 秒
            max_retries=1,  # 只重试 1 次，避免长时间等待
            retry_backoff_factor=1.5,  # 降低退避因子
        )
    return _global_http_client


async def close_global_http_client():
    """关闭全局 HTTP 客户端"""
    global _global_http_client
    if _global_http_client is not None:
        await _global_http_client.close()
        _global_http_client = None
