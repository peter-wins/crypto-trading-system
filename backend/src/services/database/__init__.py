"""
Database Service - 数据持久化服务.

Provides centralized database access with:
- Data Access Object (DAO) pattern
- Session management
- Database models
"""

from src.services.database.dao import TradingDAO
from src.services.database.session import DatabaseManager, get_db_manager, get_session
from src.services.database.models import (
    Base,
    TradeModel,
    PositionModel,
    OrderModel,
    KlineModel,
    DecisionModel,
    PortfolioSnapshotModel,
    ExperienceModel,
    StrategyModel,
    PerformanceMetricsModel,
    SystemEventModel,
    ClosedPositionModel,
)

# Backward compatibility aliases
DatabaseSession = DatabaseManager
get_session_factory = get_db_manager
Trade = TradeModel
Position = PositionModel
Balance = PortfolioSnapshotModel  # Balance 可能是 PortfolioSnapshot
Order = OrderModel
KlineData = KlineModel
DecisionLog = DecisionModel

__all__ = [
    'TradingDAO',
    'DatabaseManager',
    'DatabaseSession',
    'get_db_manager',
    'get_session_factory',
    'get_session',
    'Base',
    'TradeModel',
    'PositionModel',
    'OrderModel',
    'KlineModel',
    'DecisionModel',
    'PortfolioSnapshotModel',
    'ExperienceModel',
    'StrategyModel',
    'PerformanceMetricsModel',
    'SystemEventModel',
    'ClosedPositionModel',
    # Legacy aliases
    'Trade',
    'Position',
    'Balance',
    'Order',
    'KlineData',
    'DecisionLog',
]
