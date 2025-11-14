"""
数据库ORM模型

本模块定义SQLAlchemy ORM模型，对应PostgreSQL数据库表。
这些模型与实际数据库结构完全匹配（通过Alembic迁移创建）。
"""

from __future__ import annotations

from datetime import datetime, date, timezone
from sqlalchemy import (
    Column, String, Integer, Numeric, Boolean, DateTime, Date, BigInteger,
    Text, ForeignKey, Index, CheckConstraint, ARRAY, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class Exchange(Base):
    """交易所表"""
    __tablename__ = "exchanges"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), unique=True, nullable=False)
    api_key_encrypted = Column(Text, nullable=False)
    api_secret_encrypted = Column(Text, nullable=False)
    password_encrypted = Column(Text)
    testnet = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)


class OrderModel(Base):
    """订单表"""
    __tablename__ = "orders"

    id = Column(String(100), primary_key=True)
    client_order_id = Column(String(100), unique=True, nullable=False)
    exchange_id = Column(Integer, ForeignKey('exchanges.id'))
    symbol = Column(String(20), nullable=False)
    side = Column(String(10), nullable=False)  # buy/sell
    type = Column(String(20), nullable=False)  # market/limit/etc
    status = Column(String(20), nullable=False)

    price = Column(Numeric(20, 8))
    amount = Column(Numeric(20, 8), nullable=False)
    filled = Column(Numeric(20, 8), default=0)
    remaining = Column(Numeric(20, 8))
    cost = Column(Numeric(20, 8), default=0)
    average = Column(Numeric(20, 8))
    fee = Column(Numeric(20, 8))
    fee_currency = Column(String(10))

    stop_price = Column(Numeric(20, 8))
    take_profit_price = Column(Numeric(20, 8))
    stop_loss_price = Column(Numeric(20, 8))

    decision_id = Column(String(100))
    timestamp = Column(BigInteger, nullable=False)
    datetime = Column(DateTime, nullable=False)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
    raw_data = Column(JSONB)

    __table_args__ = (
        Index('idx_orders_symbol', 'symbol'),
        Index('idx_orders_status', 'status'),
        Index('idx_orders_datetime', 'datetime'),
        Index('idx_orders_exchange', 'exchange_id'),
        Index('idx_orders_decision', 'decision_id'),
        CheckConstraint(
            "side IN ('buy', 'sell')",
            name='orders_side_check'
        ),
        CheckConstraint(
            "status IN ('pending', 'open', 'partially_filled', 'filled', 'canceled', 'rejected', 'expired')",
            name='orders_status_check'
        ),
        CheckConstraint(
            "type IN ('market', 'limit', 'stop_loss', 'stop_loss_limit', 'take_profit', 'take_profit_limit')",
            name='orders_type_check'
        ),
    )


class TradeModel(Base):
    """成交记录表"""
    __tablename__ = "trades"

    id = Column(String(100), primary_key=True)
    order_id = Column(String(100), ForeignKey('orders.id'))
    exchange_id = Column(Integer, ForeignKey('exchanges.id'))
    symbol = Column(String(20), nullable=False)
    side = Column(String(10), nullable=False)

    price = Column(Numeric(20, 8), nullable=False)
    amount = Column(Numeric(20, 8), nullable=False)
    cost = Column(Numeric(20, 8), nullable=False)
    fee = Column(Numeric(20, 8))
    fee_currency = Column(String(10))

    timestamp = Column(BigInteger, nullable=False)
    datetime = Column(DateTime, nullable=False)
    created_at = Column(DateTime)
    raw_data = Column(JSONB)

    __table_args__ = (
        Index('idx_trades_symbol', 'symbol'),
        Index('idx_trades_datetime', 'datetime'),
        Index('idx_trades_order', 'order_id'),
        CheckConstraint(
            "side IN ('buy', 'sell')",
            name='trades_side_check'
        ),
    )


class PositionModel(Base):
    """持仓表"""
    __tablename__ = "positions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    exchange_id = Column(Integer, ForeignKey('exchanges.id'))
    symbol = Column(String(20), nullable=False)
    side = Column(String(10), nullable=False)

    amount = Column(Numeric(20, 8), nullable=False)
    entry_price = Column(Numeric(20, 8), nullable=False)
    current_price = Column(Numeric(20, 8), nullable=False)
    value = Column(Numeric(20, 8), nullable=False)

    unrealized_pnl = Column(Numeric(20, 8), default=0)
    unrealized_pnl_percentage = Column(Numeric(10, 4), default=0)

    stop_loss = Column(Numeric(20, 8))
    take_profit = Column(Numeric(20, 8))

    # 杠杆和强平价格
    leverage = Column(Integer)
    liquidation_price = Column(Numeric(20, 8))
    entry_fee = Column(Numeric(20, 8), default=0)

    # 订单关联
    entry_order_id = Column(String(100), ForeignKey('orders.id'))

    # 持仓状态
    is_open = Column(Boolean, default=True)

    opened_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime)
    closed_at = Column(DateTime)

    __table_args__ = (
        Index('idx_positions_symbol', 'symbol'),
        Index('idx_positions_exchange', 'exchange_id'),
        Index('idx_positions_opened', 'opened_at'),
        Index('idx_positions_is_open', 'is_open'),
        UniqueConstraint(
            'exchange_id',
            'symbol',
            'side',
            'is_open',
            name='uq_positions_exchange_symbol_side_open'
        ),
        CheckConstraint(
            "side IN ('long', 'short')",
            name='positions_side_check'
        ),
    )


class PortfolioSnapshotModel(Base):
    """投资组合快照表"""
    __tablename__ = "portfolio_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    exchange_id = Column(Integer, ForeignKey('exchanges.id'))

    # 新字段（与币安对齐）
    wallet_balance = Column(Numeric(20, 8), nullable=True)      # 钱包余额
    available_balance = Column(Numeric(20, 8), nullable=True)   # 可用保证金
    margin_balance = Column(Numeric(20, 8), nullable=True)      # 保证金余额
    unrealized_pnl = Column(Numeric(20, 8), nullable=True)      # 未实现盈亏

    # 旧字段（保留兼容）
    total_value = Column(Numeric(20, 8), nullable=True)         # 兼容：= wallet_balance
    cash = Column(Numeric(20, 8), nullable=True)                # 兼容：= available_balance
    positions_value = Column(Numeric(20, 8))
    total_pnl = Column(Numeric(20, 8))                          # 兼容：= unrealized_pnl

    daily_pnl = Column(Numeric(20, 8))
    total_return = Column(Numeric(10, 4))

    positions = Column(JSONB)  # 持仓详情
    snapshot_date = Column(Date, nullable=False)
    timestamp = Column(BigInteger, nullable=False)
    datetime = Column(DateTime, nullable=False)
    created_at = Column(DateTime)
    archive_reason = Column(String(50))
    is_archive = Column(Boolean, default=False)
    position_count = Column(Integer, default=0)

    __table_args__ = (
        Index('idx_portfolio_snapshots_date', 'snapshot_date'),
        Index('idx_portfolio_snapshots_exchange', 'exchange_id'),
    )


class DecisionModel(Base):
    """决策记录表"""
    __tablename__ = "decisions"

    id = Column(String(100), primary_key=True)
    decision_layer = Column(String(20), nullable=False)  # strategic/tactical

    input_context = Column(JSONB, nullable=False)
    thought_process = Column(Text, nullable=False)
    tools_used = Column(ARRAY(Text))

    decision = Column(Text, nullable=False)
    action_taken = Column(Text)
    model_used = Column(String(50))

    tokens_used = Column(Integer)
    latency_ms = Column(Integer)

    timestamp = Column(BigInteger, nullable=False)
    datetime = Column(DateTime, nullable=False)
    created_at = Column(DateTime)

    __table_args__ = (
        Index('idx_decisions_layer', 'decision_layer'),
        Index('idx_decisions_datetime', 'datetime'),
        CheckConstraint(
            "decision_layer IN ('strategic', 'tactical')",
            name='decisions_decision_layer_check'
        ),
    )


class ExperienceModel(Base):
    """交易经验表"""
    __tablename__ = "experiences"

    id = Column(String(100), primary_key=True)

    situation = Column(Text, nullable=False)
    situation_tags = Column(ARRAY(Text))
    decision = Column(Text, nullable=False)
    decision_reasoning = Column(Text, nullable=False)
    decision_id = Column(String(100), ForeignKey('decisions.id'))

    outcome = Column(String(20), nullable=False)  # success/failure
    pnl = Column(Numeric(20, 8))
    pnl_percentage = Column(Numeric(10, 4))

    reflection = Column(Text)
    lessons_learned = Column(ARRAY(Text))

    importance_score = Column(Numeric(3, 2), default=0.5)
    related_orders = Column(ARRAY(Text))
    symbol = Column(String(20))

    timestamp = Column(BigInteger, nullable=False)
    datetime = Column(DateTime, nullable=False)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)

    __table_args__ = (
        Index('idx_experiences_outcome', 'outcome'),
        Index('idx_experiences_importance', 'importance_score'),
        Index('idx_experiences_datetime', 'datetime'),
        Index('idx_experiences_symbol', 'symbol'),
        Index('idx_experiences_tags', 'situation_tags', postgresql_using='gin'),
        CheckConstraint(
            "outcome IN ('success', 'failure')",
            name='experiences_outcome_check'
        ),
    )


class StrategyModel(Base):
    """策略配置表"""
    __tablename__ = "strategies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False)
    version = Column(String(20), nullable=False)
    description = Column(Text)

    # 交易参数
    max_position_size = Column(Numeric(5, 4), nullable=False)
    max_single_trade = Column(Numeric(20, 8), nullable=False)
    max_open_positions = Column(Integer, nullable=False)

    # 风险参数
    max_daily_loss = Column(Numeric(5, 4), nullable=False)
    max_drawdown = Column(Numeric(5, 4), nullable=False)
    stop_loss_percentage = Column(Numeric(5, 2), nullable=False)
    take_profit_percentage = Column(Numeric(5, 2), nullable=False)

    # 市场参数
    trading_pairs = Column(JSONB)
    timeframes = Column(JSONB)

    is_active = Column(Boolean, default=False)
    reason_for_update = Column(Text)

    created_at = Column(DateTime)
    updated_at = Column(DateTime)


class PerformanceMetricsModel(Base):
    """绩效指标表"""
    __tablename__ = "performance_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy_id = Column(Integer, ForeignKey('strategies.id'))

    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)

    # 收益指标
    total_return = Column(Numeric(10, 4))
    annualized_return = Column(Numeric(10, 4))

    # 风险指标
    volatility = Column(Numeric(10, 4))
    max_drawdown = Column(Numeric(10, 4))
    sharpe_ratio = Column(Numeric(10, 4))
    sortino_ratio = Column(Numeric(10, 4))
    calmar_ratio = Column(Numeric(10, 4))

    # 交易统计
    total_trades = Column(Integer, default=0)
    winning_trades = Column(Integer, default=0)
    losing_trades = Column(Integer, default=0)
    win_rate = Column(Numeric(5, 2))
    avg_win = Column(Numeric(20, 8))
    avg_loss = Column(Numeric(20, 8))
    profit_factor = Column(Numeric(10, 4))

    max_consecutive_wins = Column(Integer, default=0)
    max_consecutive_losses = Column(Integer, default=0)

    created_at = Column(DateTime)

    __table_args__ = (
        Index('idx_performance_dates', 'start_date', 'end_date'),
    )


class SystemEventModel(Base):
    """系统事件表"""
    __tablename__ = "system_events"

    id = Column(String(100), primary_key=True)
    event_type = Column(String(50), nullable=False)
    severity = Column(String(20), nullable=False)  # info/warning/error/critical

    data = Column(JSONB)
    related_order_id = Column(String(100))
    related_symbol = Column(String(20))

    message = Column(Text, nullable=False)
    details = Column(Text)

    timestamp = Column(BigInteger, nullable=False)
    datetime = Column(DateTime, nullable=False)
    created_at = Column(DateTime)

    __table_args__ = (
        Index('idx_system_events_type', 'event_type'),
        Index('idx_system_events_severity', 'severity'),
        Index('idx_system_events_datetime', 'datetime'),
        Index('idx_system_events_order', 'related_order_id'),
        CheckConstraint(
            "severity IN ('info', 'warning', 'error', 'critical')",
            name='system_events_severity_check'
        ),
    )


class ClosedPositionModel(Base):
    """已平仓持仓表"""
    __tablename__ = "closed_positions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    exchange_id = Column(Integer, ForeignKey('exchanges.id'))
    symbol = Column(String(20), nullable=False)
    side = Column(String(10), nullable=False)  # buy/sell

    # 开仓信息
    entry_order_id = Column(String(100), ForeignKey('orders.id'))
    entry_price = Column(Numeric(20, 8), nullable=False)
    entry_time = Column(DateTime, nullable=False)

    # 平仓信息
    exit_order_id = Column(String(100), ForeignKey('orders.id'))
    exit_price = Column(Numeric(20, 8), nullable=False)
    exit_time = Column(DateTime, nullable=False)

    # 数量和金额
    amount = Column(Numeric(20, 8), nullable=False)
    entry_value = Column(Numeric(20, 8), nullable=False)
    exit_value = Column(Numeric(20, 8), nullable=False)

    # 盈亏
    realized_pnl = Column(Numeric(20, 8), nullable=False)
    realized_pnl_percentage = Column(Numeric(10, 4), nullable=False)

    # 手续费
    total_fee = Column(Numeric(20, 8))
    fee_currency = Column(String(10))

    # 平仓原因
    close_reason = Column(String(50))  # manual, stop_loss, take_profit, liquidation, system, unknown

    # 其他
    holding_duration_seconds = Column(Integer)
    leverage = Column(Integer)

    created_at = Column(DateTime)

    __table_args__ = (
        Index('idx_closed_positions_symbol', 'symbol'),
        Index('idx_closed_positions_exchange', 'exchange_id'),
        Index('idx_closed_positions_exit_time', 'exit_time'),
        Index('idx_closed_positions_realized_pnl', 'realized_pnl'),
        CheckConstraint(
            "side IN ('buy', 'sell')",
            name='closed_positions_side_check'
        ),
    )


class AccountSettingsModel(Base):
    """账户设置表"""
    __tablename__ = "account_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    exchange_id = Column(Integer, ForeignKey('exchanges.id'), nullable=False, unique=True)
    initial_capital = Column(Numeric(20, 8), nullable=False)
    capital_currency = Column(String(10), default='USDT')
    set_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    notes = Column(Text)

    __table_args__ = (
        Index('idx_account_settings_exchange', 'exchange_id'),
    )


class KlineModel(Base):
    """K线数据表（OHLCV）"""
    __tablename__ = "klines"

    id = Column(Integer, primary_key=True, autoincrement=True)
    exchange_id = Column(Integer, ForeignKey('exchanges.id'), nullable=False)
    symbol = Column(String(20), nullable=False)
    timeframe = Column(String(10), nullable=False)  # 5m, 15m, 1h, 4h, 1d

    timestamp = Column(BigInteger, nullable=False)  # K线开始时间戳（毫秒）
    datetime = Column(DateTime, nullable=False)     # K线开始时间

    open = Column(Numeric(20, 8), nullable=False)
    high = Column(Numeric(20, 8), nullable=False)
    low = Column(Numeric(20, 8), nullable=False)
    close = Column(Numeric(20, 8), nullable=False)
    volume = Column(Numeric(30, 8), nullable=False)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    __table_args__ = (
        # 确保同一交易对、同一时间周期、同一时间戳只有一条记录
        Index('idx_klines_unique', 'exchange_id', 'symbol', 'timeframe', 'timestamp', unique=True),
        # 查询优化索引
        Index('idx_klines_symbol_timeframe', 'symbol', 'timeframe'),
        Index('idx_klines_datetime', 'datetime'),
        Index('idx_klines_symbol_timeframe_datetime', 'symbol', 'timeframe', 'datetime'),
        CheckConstraint(
            "timeframe IN ('1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '12h', '1d', '3d', '1w')",
            name='klines_timeframe_check'
        ),
    )
