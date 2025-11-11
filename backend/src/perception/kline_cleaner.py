#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
K线数据清理任务

定期清理过期的K线数据，释放数据库存储空间
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from src.perception.kline_manager import KlineDataManager


class KlineDataCleaner:
    """K线数据清理器"""

    def __init__(
        self,
        kline_manager: KlineDataManager,
        cleanup_interval: int = 86400,  # 默认每24小时清理一次
        logger: Optional[logging.Logger] = None,
    ):
        """
        初始化清理器

        Args:
            kline_manager: K线数据管理器
            cleanup_interval: 清理间隔（秒）
            logger: 日志记录器
        """
        self.kline_manager = kline_manager
        self.cleanup_interval = cleanup_interval
        self.logger = logger or logging.getLogger(__name__)

        self.running = False
        self._task: Optional[asyncio.Task] = None
        self._last_cleanup: Optional[datetime] = None

    async def start(self) -> None:
        """启动清理任务"""
        if self._task and not self._task.done():
            self.logger.warning("清理任务已在运行")
            return

        self.running = True
        self._task = asyncio.create_task(self._cleanup_loop())
        self.logger.info(
            f"🧹 启动K线数据清理任务 (间隔: {self.cleanup_interval}秒 = {self.cleanup_interval/3600:.1f}小时)"
        )

    async def stop(self, timeout: float = 5.0) -> None:
        """停止清理任务"""
        self.running = False

        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await asyncio.wait_for(self._task, timeout=timeout)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

        self.logger.info("K线数据清理任务已停止")

    async def _cleanup_loop(self) -> None:
        """清理主循环"""
        try:
            while self.running:
                try:
                    # 执行清理
                    await self._perform_cleanup()

                    # 等待下次清理
                    await asyncio.sleep(self.cleanup_interval)

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    self.logger.error(f"清理任务错误: {e}", exc_info=True)
                    await asyncio.sleep(self.cleanup_interval)

        except Exception as e:
            self.logger.error(f"清理循环异常: {e}")

    async def _perform_cleanup(self) -> None:
        """执行一次清理"""
        self.logger.info("开始清理过期K线数据...")

        try:
            # 调用管理器的清理方法
            stats = await self.kline_manager.cleanup_expired_data()

            # 统计总删除数
            total_deleted = sum(stats.values())

            if total_deleted > 0:
                self.logger.info(f"✅ 清理完成，共删除 {total_deleted} 条过期K线数据")
                for timeframe, count in stats.items():
                    if count > 0:
                        self.logger.info(f"  {timeframe}: {count} 条")
            else:
                self.logger.info("✅ 清理完成，无过期数据需要删除")

            # 更新最后清理时间
            self._last_cleanup = datetime.now(timezone.utc)

        except Exception as e:
            self.logger.error(f"执行清理失败: {e}", exc_info=True)

    async def cleanup_now(self) -> None:
        """立即执行一次清理"""
        self.logger.info("手动触发清理...")
        await self._perform_cleanup()

    def get_status(self) -> dict:
        """获取清理器状态"""
        return {
            "running": self.running,
            "cleanup_interval": self.cleanup_interval,
            "last_cleanup": self._last_cleanup.isoformat() if self._last_cleanup else None,
            "next_cleanup_in": None,  # TODO: 计算下次清理时间
        }
