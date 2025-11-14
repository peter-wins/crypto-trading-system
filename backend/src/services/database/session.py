"""
数据库会话管理

本模块管理数据库连接和会话。
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker
)
from sqlalchemy.pool import NullPool

from src.core.logger import get_logger
from .models import Base


logger = get_logger(__name__)


class DatabaseManager:
    """数据库管理器"""

    def __init__(self, database_url: str, echo: bool = False):
        """
        初始化数据库管理器

        Args:
            database_url: 数据库连接URL（postgresql://...）
            echo: 是否打印SQL语句
        """
        # 将postgresql://转换为postgresql+asyncpg://
        if database_url.startswith("postgresql://"):
            database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

        self.database_url = database_url
        self.echo = echo
        self.engine = None
        self.session_factory = None
        self.logger = logger

    def initialize(self) -> None:
        """初始化数据库引擎和会话工厂"""
        try:
            self.engine = create_async_engine(
                self.database_url,
                echo=self.echo,
                pool_size=20,  # 连接池大小
                max_overflow=10,  # 超过pool_size后最多再创建的连接数
                pool_pre_ping=True,  # 使用前ping测试连接
                future=True
            )

            self.session_factory = async_sessionmaker(
                self.engine,
                class_=AsyncSession,
                expire_on_commit=False
            )

            self.logger.info("Database manager initialized")

        except Exception as e:
            self.logger.error(f"Failed to initialize database: {e}")
            raise

    async def create_tables(self) -> None:
        """创建所有表（仅用于测试）"""
        if not self.engine:
            self.initialize()

        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            self.logger.info("Created all database tables")

    async def drop_tables(self) -> None:
        """删除所有表（仅用于测试）"""
        if not self.engine:
            self.initialize()

        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            self.logger.info("Dropped all database tables")

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        获取数据库会话（上下文管理器）

        Usage:
            async with db_manager.get_session() as session:
                # 使用session
                pass
        """
        if not self.session_factory:
            self.initialize()

        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    async def get_dao(self, default_exchange_name: str = "binance"):
        """
        获取DAO实例

        Args:
            default_exchange_name: 默认交易所名称

        Returns:
            TradingDAO实例，带有活跃的数据库会话
        """
        from .dao import TradingDAO

        if not self.session_factory:
            self.initialize()

        session = self.session_factory()
        return TradingDAO(session, default_exchange_name)

    async def close(self) -> None:
        """关闭数据库连接"""
        if self.engine:
            await self.engine.dispose()
            self.logger.info("Closed database connections")


# 全局数据库管理器实例
_db_manager: DatabaseManager | None = None


def get_db_manager(database_url: str | None = None, echo: bool = False) -> DatabaseManager:
    """
    获取全局数据库管理器实例

    Args:
        database_url: 数据库连接URL
        echo: 是否打印SQL语句

    Returns:
        DatabaseManager实例
    """
    global _db_manager

    if _db_manager is None:
        if database_url is None:
            raise ValueError("database_url is required for first initialization")
        _db_manager = DatabaseManager(database_url, echo)
        _db_manager.initialize()

    return _db_manager


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    获取数据库会话（便捷函数）

    Usage:
        async with get_session() as session:
            # 使用session
            pass
    """
    db_manager = get_db_manager()
    async with db_manager.get_session() as session:
        yield session
