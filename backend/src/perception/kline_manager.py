#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
K线数据管理器

实现多层缓存策略的K线数据获取和管理:
1. 内存缓存（最快，数据最新）
2. Redis缓存（次快，近期数据）
3. PostgreSQL数据库（历史数据）
4. API实时获取（兜底方案）
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from src.perception.kline_config import (
    KLINE_CONFIGS,
    DEFAULT_FETCH_STRATEGY,
    DataFetchStrategy,
    TimeframeConfig,
)


class KlineDataManager:
    """
    K线数据管理器

    职责:
    1. 多层缓存数据获取（内存 → Redis → DB → API）
    2. 多周期K线采集调度
    3. 过期数据清理
    4. 数据一致性保证
    """

    def __init__(
        self,
        symbols: List[str],
        market_collector: Any,
        short_term_memory: Any,
        dao: Optional[Any] = None,
        db_manager: Optional[Any] = None,
        strategy: DataFetchStrategy = DEFAULT_FETCH_STRATEGY,
        logger: Optional[logging.Logger] = None,
    ):
        """
        初始化K线数据管理器

        Args:
            symbols: 交易对列表
            market_collector: 市场数据采集器（API）
            short_term_memory: Redis短期内存
            dao: 数据库DAO (已废弃，使用db_manager)
            db_manager: 数据库管理器（用于创建独立session）
            strategy: 数据获取策略
            logger: 日志记录器
        """
        self.symbols = symbols
        self.market_collector = market_collector
        self.short_term_memory = short_term_memory
        self.dao = dao  # 保留用于向后兼容
        self.db_manager = db_manager
        self.strategy = strategy
        self.logger = logger or logging.getLogger(__name__)

        # 三层缓存
        self._memory_cache: Dict[str, Dict[str, Any]] = {}  # {cache_key: {data, timestamp}}
        self._last_collection: Dict[str, float] = {}  # {task_key: timestamp}

        # 运行控制
        self.running = False
        self._collection_tasks: List[asyncio.Task] = []

    def _get_cache_key(self, symbol: str, timeframe: str) -> str:
        """生成缓存键"""
        return f"kline:{symbol}:{timeframe}"

    def _get_task_key(self, symbol: str, timeframe: str) -> str:
        """生成任务键"""
        return f"{symbol}:{timeframe}"

    async def start(self) -> None:
        """启动多周期K线采集任务"""
        if self.running:
            self.logger.warning("K线采集任务已在运行")
            return

        self.running = True
        self.logger.info("🚀 启动多周期K线采集任务")

        # 为每个交易对和时间周期创建采集任务
        for symbol in self.symbols:
            for timeframe, config in KLINE_CONFIGS.items():
                task = asyncio.create_task(
                    self._collection_loop(symbol, timeframe, config)
                )
                self._collection_tasks.append(task)

                self.logger.info(
                    f"  启动 {symbol} {timeframe} 采集任务 (间隔: {config.collection_interval}秒)"
                )

        self.logger.info(f"✅ 已启动 {len(self._collection_tasks)} 个采集任务")

    async def stop(self, timeout: float = 5.0) -> None:
        """停止所有采集任务"""
        self.running = False
        self.logger.info("正在停止K线采集任务...")

        # 取消所有任务
        for task in self._collection_tasks:
            if not task.done():
                task.cancel()

        # 等待任务完成
        if self._collection_tasks:
            await asyncio.wait(self._collection_tasks, timeout=timeout)

        self._collection_tasks.clear()
        self.logger.info("✅ K线采集任务已停止")

    async def _collection_loop(
        self,
        symbol: str,
        timeframe: str,
        config: TimeframeConfig
    ) -> None:
        """单个时间周期的采集循环"""
        task_key = self._get_task_key(symbol, timeframe)

        try:
            while self.running:
                try:
                    # 检查是否需要采集
                    last_time = self._last_collection.get(task_key, 0)
                    elapsed = time.time() - last_time

                    if elapsed < config.collection_interval:
                        # 还未到采集时间，等待
                        await asyncio.sleep(config.collection_interval - elapsed)
                        continue

                    # 执行采集
                    await self._collect_and_save(symbol, timeframe, config)

                    # 更新最后采集时间
                    self._last_collection[task_key] = time.time()

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    self.logger.error(
                        f"采集 {symbol} {timeframe} 失败: {e}",
                        exc_info=True
                    )
                    await asyncio.sleep(config.collection_interval)

        except Exception as e:
            self.logger.error(f"采集循环异常 {symbol} {timeframe}: {e}")

    async def _collect_and_save(
        self,
        symbol: str,
        timeframe: str,
        config: TimeframeConfig
    ) -> None:
        """采集K线并保存到各层缓存"""
        try:
            if not hasattr(self, "_latest_timestamp"):
                self._latest_timestamp = {}
            # 1. 从API获取最新K线
            cache_key = self._get_cache_key(symbol, timeframe)
            last_ts = self._latest_timestamp.get(cache_key)

            fetch_since = None
            fetch_limit = config.limit
            incremental_attempted = False

            if last_ts:
                fetch_since = int(last_ts + 1)
                fetch_limit = min(getattr(config, "incremental_limit", config.limit), config.limit)
                incremental_attempted = True

            klines = await self.market_collector.get_ohlcv(
                symbol,
                timeframe=timeframe,
                limit=fetch_limit,
                since=fetch_since
            )

            if incremental_attempted and not klines:
                self.logger.debug(
                    "%s %s 增量拉取无数据，回退全量", symbol, timeframe
                )
                fetch_since = None
                klines = await self.market_collector.get_ohlcv(
                    symbol,
                    timeframe=timeframe,
                    limit=config.limit,
                    since=None
                )

            if not klines:
                self.logger.warning(f"{symbol} {timeframe} 无可用K线数据")
                return

            # 2. 更新内存缓存
            cache_key = self._get_cache_key(symbol, timeframe)
            if fetch_since and cache_key in self._memory_cache:
                existing = self._memory_cache[cache_key]["data"]
                existing_ts = {k.timestamp for k in existing}
                merged = existing + [k for k in klines if k.timestamp not in existing_ts]
                merged.sort(key=lambda item: item.timestamp)
                trimmed = merged[-config.limit :]
                cache_data = trimmed
            else:
                cache_data = klines[-config.limit :]

            self._memory_cache[cache_key] = {
                "data": cache_data,
                "timestamp": time.time(),
                "symbol": symbol,
                "timeframe": timeframe,
            }
            self._latest_timestamp[cache_key] = cache_data[-1].timestamp

            # 3. 保存到数据库（使用独立session避免并发冲突）
            if self.db_manager:
                dao = None
                try:
                    # 为每次保存创建独立的DAO实例（带独立session）
                    dao = await self.db_manager.get_dao()
                    saved_count = await dao.save_klines(
                        symbol=symbol,
                        timeframe=timeframe,
                        klines=klines
                    )
                    # 提交事务
                    await dao.session.commit()
                    self.logger.debug(
                        f"保存 {symbol} {timeframe} {saved_count} 根K线到数据库"
                    )
                except Exception as db_error:
                    # 回滚事务
                    if dao and dao.session:
                        await dao.session.rollback()
                    self.logger.warning(
                        f"保存K线到数据库失败 {symbol} {timeframe}: {db_error}"
                    )
                finally:
                    # 关闭session
                    if dao and dao.session:
                        await dao.session.close()
            elif self.dao:
                # 向后兼容：如果传入了dao，使用旧方式（不推荐，有并发问题）
                try:
                    saved_count = await self.dao.save_klines(
                        symbol=symbol,
                        timeframe=timeframe,
                        klines=klines
                    )
                    await self.dao.session.commit()
                    self.logger.debug(
                        f"保存 {symbol} {timeframe} {saved_count} 根K线到数据库"
                    )
                except Exception as db_error:
                    await self.dao.session.rollback()
                    self.logger.warning(
                        f"保存K线到数据库失败 {symbol} {timeframe}: {db_error}"
                    )

            # 4. 可选: 保存到Redis（用于跨进程共享）
            # TODO: 实现Redis缓存

        except Exception as e:
            self.logger.error(f"采集保存K线失败 {symbol} {timeframe}: {e}")

    async def get_klines(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 100,
        use_cache: bool = True
    ) -> List[Any]:
        """
        智能获取K线数据（多层缓存策略）

        优先级:
        1. 内存缓存（最快）
        2. Redis缓存（次快）
        3. 数据库（历史数据）
        4. API实时获取（兜底）

        Args:
            symbol: 交易对
            timeframe: 时间周期
            limit: 返回数量
            use_cache: 是否使用缓存

        Returns:
            K线数据列表
        """
        cache_key = self._get_cache_key(symbol, timeframe)

        # 层1: 内存缓存
        if use_cache and cache_key in self._memory_cache:
            cached = self._memory_cache[cache_key]
            age = time.time() - cached["timestamp"]

            if age < self.strategy.memory_cache_ttl:
                self.logger.debug(
                    f"[内存缓存命中] {symbol} {timeframe} (年龄: {age:.1f}秒)"
                )
                return cached["data"][:limit]

        # 层2: Redis缓存
        # TODO: 实现Redis缓存读取
        # if use_cache:
        #     redis_data = await self._get_from_redis(symbol, timeframe, limit)
        #     if redis_data:
        #         return redis_data

        # 层3: 数据库（使用独立session）
        if use_cache and self.db_manager:
            dao = None
            try:
                dao = await self.db_manager.get_dao()
                db_klines = await dao.get_klines(
                    symbol=symbol,
                    timeframe=timeframe,
                    limit=limit
                )
                if db_klines:
                    self.logger.debug(
                        f"[数据库命中] {symbol} {timeframe} ({len(db_klines)} 条)"
                    )
                    # 转换为OHLCV对象格式（如需要）
                    # TODO: 转换数据格式
                    return db_klines
            except Exception as e:
                self.logger.warning(f"从数据库获取K线失败: {e}")
            finally:
                if dao and dao.session:
                    await dao.session.close()
        elif use_cache and self.dao:
            # 向后兼容
            try:
                db_klines = await self.dao.get_klines(
                    symbol=symbol,
                    timeframe=timeframe,
                    limit=limit
                )
                if db_klines:
                    self.logger.debug(
                        f"[数据库命中] {symbol} {timeframe} ({len(db_klines)} 条)"
                    )
                    return db_klines
            except Exception as e:
                self.logger.warning(f"从数据库获取K线失败: {e}")

        # 层4: API实时获取（兜底）
        if self.strategy.enable_api_fallback:
            try:
                self.logger.debug(f"[API获取] {symbol} {timeframe}")
                klines = await self.market_collector.get_ohlcv(
                    symbol,
                    timeframe=timeframe,
                    limit=limit
                )

                # 更新内存缓存
                if klines:
                    self._memory_cache[cache_key] = {
                        "data": klines,
                        "timestamp": time.time(),
                        "symbol": symbol,
                        "timeframe": timeframe,
                    }

                return klines

            except Exception as e:
                self.logger.error(f"从API获取K线失败: {e}")
                return []

        return []

    async def cleanup_expired_data(self) -> Dict[str, int]:
        """
        清理过期数据（使用独立session）

        Returns:
            清理统计 {timeframe: deleted_count}
        """
        if not self.db_manager and not self.dao:
            self.logger.warning("数据库管理器未配置，无法清理数据")
            return {}

        stats = {}
        # 使用不带时区的datetime，因为数据库字段是TIMESTAMP WITHOUT TIME ZONE
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        dao = None

        try:
            # 创建独立session用于清理操作
            if self.db_manager:
                dao = await self.db_manager.get_dao()
            else:
                dao = self.dao  # 向后兼容

            async with dao.session.begin():
                for timeframe, config in KLINE_CONFIGS.items():
                    if config.retention_days == 0:
                        # 永久保留
                        continue

                    # 计算过期时间（不带时区）
                    cutoff_date = now - timedelta(days=config.retention_days)

                    # 删除过期数据
                    from sqlalchemy import delete
                    from src.database.models import KlineModel

                    result = await dao.session.execute(
                        delete(KlineModel).where(
                            KlineModel.timeframe == timeframe,
                            KlineModel.datetime < cutoff_date
                        )
                    )

                    deleted_count = result.rowcount
                    stats[timeframe] = deleted_count

                    if deleted_count > 0:
                        self.logger.info(
                            f"清理 {timeframe} 过期数据: {deleted_count} 条 "
                            f"(早于 {cutoff_date.date()})"
                        )

            return stats

        except Exception as e:
            self.logger.error(f"清理过期数据失败: {e}")
            return stats
        finally:
            # 如果是新创建的session，需要关闭
            if dao and dao is not self.dao and dao.session:
                await dao.session.close()

    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        stats = {
            "memory_cache_size": len(self._memory_cache),
            "active_tasks": len([t for t in self._collection_tasks if not t.done()]),
            "timeframes": {},
        }

        # 按时间周期统计
        for cache_key, cached in self._memory_cache.items():
            tf = cached.get("timeframe")
            if tf not in stats["timeframes"]:
                stats["timeframes"][tf] = {
                    "count": 0,
                    "total_klines": 0,
                    "avg_age": 0,
                }

            stats["timeframes"][tf]["count"] += 1
            stats["timeframes"][tf]["total_klines"] += len(cached["data"])
            stats["timeframes"][tf]["avg_age"] += time.time() - cached["timestamp"]

        # 计算平均值
        for tf_stats in stats["timeframes"].values():
            if tf_stats["count"] > 0:
                tf_stats["avg_age"] /= tf_stats["count"]

        return stats
        self._latest_timestamp: Dict[str, int] = {}
