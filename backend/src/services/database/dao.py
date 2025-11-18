"""
数据访问对象（DAO）层

本模块提供数据库操作的高级接口，将 Pydantic 模型转换为 SQLAlchemy ORM 模型。
"""

from __future__ import annotations

from datetime import datetime, date, timezone
from decimal import Decimal
from typing import List, Optional, Dict, Any
from sqlalchemy import select, and_, desc
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.logger import get_logger
from src.models.trade import Order, Trade, Position
from src.models.portfolio import Portfolio
from src.models.decision import DecisionRecord
from src.models.memory import TradingExperience
from src.models.event import SystemEvent

from .models import (
    Exchange, OrderModel, TradeModel, PositionModel, PortfolioSnapshotModel,
    DecisionModel, ExperienceModel, SystemEventModel, KlineModel, ClosedPositionModel
)


logger = get_logger(__name__)


class TradingDAO:
    """交易数据访问对象"""

    def __init__(self, session: AsyncSession, default_exchange_name: str = "binance"):
        """
        初始化DAO

        Args:
            session: 数据库会话
            default_exchange_name: 默认交易所名称
        """
        self.session = session
        self.logger = logger
        self.default_exchange_name = default_exchange_name
        self._exchange_cache: Dict[str, int] = {}

    @staticmethod
    def _make_naive(dt: datetime) -> datetime:
        """移除datetime的时区信息，因为数据库使用TIMESTAMP WITHOUT TIME ZONE"""
        if dt.tzinfo is not None:
            return dt.replace(tzinfo=None)
        return dt

    def _convert_opened_at(self, opened_at: Optional[Any]) -> datetime:
        """将 Position.opened_at 转换为数据库可用的 datetime（UTC时间，无时区信息）"""
        if opened_at is None:
            return datetime.now(timezone.utc).replace(tzinfo=None)

        if isinstance(opened_at, datetime):
            return self._make_naive(opened_at)

        try:
            value = float(opened_at)
        except (TypeError, ValueError):
            return datetime.now(timezone.utc).replace(tzinfo=None)

        # Binance/CCXT 返回毫秒时间戳，需要转换为秒
        if value > 1e12:
            value /= 1000.0
        elif value > 1e10:  # 微秒
            value /= 1e6

        try:
            dt_obj = datetime.fromtimestamp(value, tz=timezone.utc)
            return self._make_naive(dt_obj)
        except (OSError, OverflowError, ValueError):
            return datetime.now(timezone.utc).replace(tzinfo=None)

    async def _get_or_create_exchange_id(self, exchange_name: Optional[str] = None) -> int:
        """
        获取或创建交易所ID

        Args:
            exchange_name: 交易所名称，默认使用 self.default_exchange_name

        Returns:
            交易所ID
        """
        name = exchange_name or self.default_exchange_name

        # 检查缓存
        if name in self._exchange_cache:
            return self._exchange_cache[name]

        # 查询数据库（使用独立查询避免session冲突）
        result = await self.session.execute(
            select(Exchange.id).where(Exchange.name == name)
        )
        exchange_id = result.scalar_one_or_none()

        if not exchange_id:
            # 创建新交易所需要在独立事务中完成
            # 为避免并发问题，这里抛出异常要求预先创建
            raise ValueError(
                f"Exchange '{name}' not found in database. "
                f"Please create it first using insert_exchange.py"
            )

        # 缓存ID
        self._exchange_cache[name] = exchange_id
        return exchange_id

    # ==================== Order Methods ====================

    async def save_order(self, order: Order, exchange_name: Optional[str] = None) -> bool:
        """保存或更新订单（UPSERT）"""
        try:
            exchange_id = await self._get_or_create_exchange_id(exchange_name or order.exchange)

            # 检查订单是否已存在
            result = await self.session.execute(
                select(OrderModel).where(OrderModel.id == order.id)
            )
            existing_order = result.scalar_one_or_none()

            if existing_order:
                # 更新现有订单
                existing_order.status = order.status.value
                existing_order.filled = order.filled
                existing_order.remaining = order.remaining
                existing_order.cost = order.cost
                existing_order.average = order.average
                existing_order.fee = order.fee
                existing_order.fee_currency = order.fee_currency if hasattr(order, 'fee_currency') else None
                existing_order.updated_at = datetime.now(timezone.utc)
                existing_order.raw_data = order.info or {}

                self.logger.debug(
                    f"更新订单 {order.id}: status={order.status.value}, "
                    f"filled={order.filled}/{order.amount}"
                )
            else:
                # 插入新订单
                order_model = OrderModel(
                    id=order.id,
                    client_order_id=order.client_order_id or order.id,
                    exchange_id=exchange_id,
                    symbol=order.symbol,
                    side=order.side.value,
                    type=order.type.value,
                    status=order.status.value,
                    price=order.price,
                    amount=order.amount,
                    filled=order.filled,
                    remaining=order.remaining,
                    cost=order.cost,
                    average=order.average,
                    fee=order.fee,
                    fee_currency=order.fee_currency if hasattr(order, 'fee_currency') else None,
                    stop_price=order.stop_price,
                    take_profit_price=order.take_profit_price,
                    stop_loss_price=order.stop_loss_price,
                    timestamp=order.timestamp,
                    datetime=self._make_naive(order.dt),
                    raw_data=order.info or {}
                )
                self.session.add(order_model)
                self.logger.debug(f"新增订单 {order.id}: {order.symbol} {order.side.value}")

            await self.session.flush()
            return True

        except Exception as e:
            self.logger.error(f"Failed to save order {order.id}: {e}")
            return False

    # ==================== Trade Methods ====================

    async def save_trade(self, trade: Trade, exchange_name: Optional[str] = None) -> bool:
        """保存成交记录"""
        try:
            exchange_id = await self._get_or_create_exchange_id(exchange_name)

            trade_model = TradeModel(
                id=trade.id,
                order_id=trade.order_id,
                exchange_id=exchange_id,
                symbol=trade.symbol,
                side=trade.side.value,
                price=trade.price,
                amount=trade.amount,
                cost=trade.cost,
                fee=trade.fee if hasattr(trade, 'fee') else None,
                fee_currency=trade.fee_currency if hasattr(trade, 'fee_currency') else None,
                timestamp=trade.timestamp,
                datetime=self._make_naive(trade.dt),
                raw_data=trade.info or {}
            )

            self.session.add(trade_model)
            await self.session.flush()
            return True

        except Exception as e:
            self.logger.error(f"Failed to save trade {trade.id}: {e}")
            return False

    # ==================== Position Methods ====================

    async def save_position(
        self,
        position: Position,
        exchange_name: Optional[str] = None
    ) -> bool:
        """
        保存或更新持仓（UPSERT）

        注意：positions 表存储当前活跃持仓，每个 (exchange_id, symbol, side, is_open=True) 只能有一条记录。
        如果已存在相同symbol和side的开仓记录，则更新；否则插入新记录。
        支持 HEDGE 模式下同一 symbol 的多空双向持仓。
        """
        try:
            exchange_id = await self._get_or_create_exchange_id(exchange_name)

            # 查找是否已存在该symbol和side的开仓记录（支持双向持仓）
            result = await self.session.execute(
                select(PositionModel).where(
                    and_(
                        PositionModel.exchange_id == exchange_id,
                        PositionModel.symbol == position.symbol,
                        PositionModel.side == position.side.value,  # 增加 side 条件以支持双向持仓
                        PositionModel.is_open == True
                    )
                )
            )
            existing_position = result.scalar_one_or_none()

            entry_order_id = getattr(position, "entry_order_id", None)
            opened_at = self._convert_opened_at(getattr(position, "opened_at", None))

            if existing_position:
                # 更新现有持仓
                existing_position.side = position.side.value
                existing_position.amount = position.amount
                existing_position.entry_price = position.entry_price
                existing_position.current_price = position.current_price
                existing_position.value = position.value
                existing_position.unrealized_pnl = position.unrealized_pnl
                existing_position.unrealized_pnl_percentage = position.unrealized_pnl_percentage
                existing_position.stop_loss = position.stop_loss
                existing_position.take_profit = position.take_profit
                existing_position.leverage = position.leverage
                existing_position.liquidation_price = position.liquidation_price
                if getattr(position, "entry_fee", None) is not None:
                    existing_position.entry_fee = position.entry_fee
                existing_position.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
                if entry_order_id:
                    existing_position.entry_order_id = entry_order_id
                if position.opened_at:
                    existing_position.opened_at = opened_at
            else:
                # 插入新持仓
                position_model = PositionModel(
                    exchange_id=exchange_id,
                    symbol=position.symbol,
                    side=position.side.value,
                    amount=position.amount,
                    entry_price=position.entry_price,
                    current_price=position.current_price,
                    value=position.value,
                    unrealized_pnl=position.unrealized_pnl,
                    unrealized_pnl_percentage=position.unrealized_pnl_percentage,
                    stop_loss=position.stop_loss,
                    take_profit=position.take_profit,
                    leverage=position.leverage,
                    liquidation_price=position.liquidation_price,
                    entry_fee=position.entry_fee or Decimal('0'),
                    is_open=True,
                    entry_order_id=entry_order_id,
                    opened_at=opened_at
                )
                self.session.add(position_model)

            await self.session.flush()
            return True

        except Exception as e:
            self.logger.error(f"Failed to save position {position.symbol}: {e}")
            return False

    async def get_position_by_symbol_side(
        self,
        symbol: str,
        side: str,
        exchange_name: Optional[str] = None,
    ) -> Optional[PositionModel]:
        """获取指定 symbol/side 的当前持仓"""
        try:
            exchange_id = await self._get_or_create_exchange_id(exchange_name)
            result = await self.session.execute(
                select(PositionModel).where(
                    and_(
                        PositionModel.exchange_id == exchange_id,
                        PositionModel.symbol == symbol,
                        PositionModel.side == side,
                        PositionModel.is_open == True,
                    )
                )
            )
            return result.scalar_one_or_none()
        except Exception as e:
            self.logger.error(f"Failed to fetch position {symbol} {side}: {e}")
            return None

    # ==================== Portfolio Methods ====================

    async def update_latest_portfolio_snapshot(
        self,
        wallet_balance: float,
        available_balance: float,
        margin_balance: float,
        unrealized_pnl: float,
        positions: List[Any],
        exchange_name: Optional[str] = None
    ) -> bool:
        """
        更新最新的投资组合快照（用于 AccountSyncService 每 10 秒同步）

        如果存在记录则更新最新一条，否则创建新记录
        """
        try:
            from datetime import datetime
            from sqlalchemy import select, desc

            exchange_id = await self._get_or_create_exchange_id(exchange_name)

            # 查询最新的快照记录
            stmt = (
                select(PortfolioSnapshotModel)
                .where(PortfolioSnapshotModel.exchange_id == exchange_id)
                .order_by(desc(PortfolioSnapshotModel.datetime))
                .limit(1)
            )
            result = await self.session.execute(stmt)
            latest_snapshot = result.scalar_one_or_none()

            now = datetime.now(timezone.utc).replace(tzinfo=None)
            snapshot_date = now.date()

            # 准备持仓数据
            positions_data = [{
                "symbol": p.symbol,
                "side": p.side,
                "amount": float(p.amount),
                "entry_price": float(p.entry_price),
                "current_price": float(p.current_price),
                "value": float(p.value),
                "pnl": float(p.unrealized_pnl),
                "leverage": p.leverage if p.leverage else None,
                "liquidation_price": float(p.liquidation_price) if p.liquidation_price else None,
                "stop_loss": float(p.stop_loss) if p.stop_loss else None,
                "take_profit": float(p.take_profit) if p.take_profit else None
            } for p in positions]

            positions_value = sum(p.value for p in positions)
            total_value = wallet_balance  # 总资产 = 钱包余额

            if latest_snapshot:
                # 更新现有记录
                latest_snapshot.wallet_balance = wallet_balance
                latest_snapshot.available_balance = available_balance
                latest_snapshot.margin_balance = margin_balance
                latest_snapshot.unrealized_pnl = unrealized_pnl
                latest_snapshot.total_value = total_value
                latest_snapshot.cash = available_balance
                latest_snapshot.positions_value = positions_value
                latest_snapshot.positions = positions_data
                latest_snapshot.snapshot_date = snapshot_date
                latest_snapshot.timestamp = int(now.timestamp())
                latest_snapshot.datetime = now
                latest_snapshot.updated_at = now

                self.logger.debug(
                    f"已更新最新快照: 总资产={total_value:.2f}, "
                    f"持仓数={len(positions)}"
                )
            else:
                # 首次创建记录
                snapshot_model = PortfolioSnapshotModel(
                    exchange_id=exchange_id,
                    wallet_balance=wallet_balance,
                    available_balance=available_balance,
                    margin_balance=margin_balance,
                    unrealized_pnl=unrealized_pnl,
                    total_value=total_value,
                    cash=available_balance,
                    positions_value=positions_value,
                    positions=positions_data,
                    snapshot_date=snapshot_date,
                    timestamp=int(now.timestamp()),
                    datetime=now
                )
                self.session.add(snapshot_model)

                self.logger.debug(
                    f"已创建首个快照: 总资产={total_value:.2f}, "
                    f"持仓数={len(positions)}"
                )

            await self.session.flush()
            return True

        except Exception as e:
            self.logger.error(f"Failed to update latest portfolio snapshot: {e}")
            return False

    async def save_portfolio_snapshot(
        self,
        portfolio: Portfolio,
        exchange_name: Optional[str] = None,
        *,
        archive_reason: Optional[str] = None,
        is_archive: bool = False,
        position_count: Optional[int] = None,
    ) -> bool:
        """保存投资组合快照"""
        try:
            exchange_id = await self._get_or_create_exchange_id(exchange_name)
            snapshot_date = portfolio.dt.date()

            positions_data = [{
                "symbol": p.symbol,
                "side": p.side.value,
                "amount": float(p.amount),
                "entry_price": float(p.entry_price),
                "current_price": float(p.current_price),
                "value": float(p.value),
                "pnl": float(p.unrealized_pnl),
                "pnl_pct": float(p.unrealized_pnl_percentage or 0),
                "leverage": p.leverage if p.leverage else None,
                "liquidation_price": float(p.liquidation_price) if p.liquidation_price else None,
                "stop_loss": float(p.stop_loss) if p.stop_loss else None,
                "take_profit": float(p.take_profit) if p.take_profit else None
            } for p in portfolio.positions]

            snapshot_model = PortfolioSnapshotModel(
                exchange_id=exchange_id,
                wallet_balance=portfolio.wallet_balance,
                available_balance=portfolio.available_balance,
                margin_balance=portfolio.margin_balance,
                unrealized_pnl=portfolio.unrealized_pnl,
                total_value=portfolio.total_value,
                cash=portfolio.cash,
                positions_value=sum(p.value for p in portfolio.positions),
                total_pnl=portfolio.total_pnl,
                daily_pnl=portfolio.daily_pnl,
                total_return=portfolio.total_return,
                positions=positions_data,
                snapshot_date=snapshot_date,
                timestamp=portfolio.timestamp,
                datetime=self._make_naive(portfolio.dt),
                archive_reason=archive_reason,
                is_archive=is_archive,
                position_count=position_count if position_count is not None else len(portfolio.positions),
            )
            self.session.add(snapshot_model)

            await self.session.flush()
            return True

        except Exception as e:
            self.logger.error(f"Failed to save portfolio snapshot: {e}")
            return False

    # ==================== Decision Methods ====================

    async def save_decision(self, decision: DecisionRecord) -> bool:
        """保存决策记录"""
        try:
            decision_model = DecisionModel(
                id=decision.id,
                decision_layer=decision.decision_layer,
                input_context=decision.input_context or {},
                thought_process=decision.thought_process or "",
                tools_used=decision.tools_used or [],
                decision=decision.decision or "",
                action_taken=decision.action_taken,
                model_used=decision.model_used,
                tokens_used=decision.tokens_used,
                latency_ms=decision.latency_ms,
                timestamp=decision.timestamp,
                datetime=self._make_naive(decision.dt)
            )

            self.session.add(decision_model)
            await self.session.flush()
            return True

        except Exception as e:
            self.logger.error(f"Failed to save decision {decision.id}: {e}")
            return False

    async def get_decisions(
        self,
        limit: Optional[int] = None,
        decision_layer: Optional[str] = None,
        start_datetime: Optional[datetime] = None,
        end_datetime: Optional[datetime] = None
    ) -> List[DecisionModel]:
        """
        查询决策记录

        Args:
            limit: 返回数量限制，None表示不限制
            decision_layer: 决策层级过滤 (strategic/tactical)
            start_datetime: 开始时间
            end_datetime: 结束时间

        Returns:
            决策记录列表
        """
        try:
            query = select(DecisionModel).order_by(desc(DecisionModel.datetime))

            filters = []
            if decision_layer:
                filters.append(DecisionModel.decision_layer == decision_layer)
            if start_datetime:
                filters.append(DecisionModel.datetime >= self._make_naive(start_datetime))
            if end_datetime:
                filters.append(DecisionModel.datetime <= self._make_naive(end_datetime))

            if filters:
                query = query.where(and_(*filters))

            if limit is not None:
                query = query.limit(limit)

            result = await self.session.execute(query)
            return list(result.scalars().all())

        except Exception as e:
            self.logger.error(f"Failed to get decisions: {e}")
            return []

    async def get_decision_by_id(self, decision_id: str) -> Optional[DecisionModel]:
        """根据ID获取决策记录"""
        try:
            query = select(DecisionModel).where(DecisionModel.id == decision_id)
            result = await self.session.execute(query)
            return result.scalar_one_or_none()
        except Exception as e:
            self.logger.error(f"Failed to get decision {decision_id}: {e}")
            return None

    # ==================== Experience Methods ====================

    async def save_experience(self, experience: TradingExperience) -> bool:
        """保存交易经验"""
        try:
            experience_model = ExperienceModel(
                id=experience.id,
                situation=experience.situation,
                situation_tags=experience.tags or [],
                decision=experience.decision,
                decision_reasoning=experience.decision_reasoning or "",
                outcome=experience.outcome,
                pnl=experience.pnl,
                pnl_percentage=experience.pnl_percentage,
                reflection=experience.reflection,
                lessons_learned=experience.lessons_learned or [],
                importance_score=Decimal(str(experience.importance_score)),
                timestamp=experience.timestamp,
                datetime=self._make_naive(experience.dt)
            )

            self.session.add(experience_model)
            await self.session.flush()
            return True

        except Exception as e:
            self.logger.error(f"Failed to save experience {experience.id}: {e}")
            return False

    # ==================== System Event Methods ====================

    async def save_system_event(self, event: SystemEvent) -> bool:
        """保存系统事件"""
        try:
            event_model = SystemEventModel(
                id=event.id,
                event_type=event.event_type.value,
                severity=event.severity,
                message=event.message,
                details=event.details,
                data=event.data or {},
                related_order_id=event.related_order_id,
                related_symbol=event.related_symbol,
                timestamp=event.timestamp,
                datetime=self._make_naive(event.dt)
            )

            self.session.add(event_model)
            await self.session.flush()
            return True

        except Exception as e:
            self.logger.error(f"Failed to save system event {event.id}: {e}")
            return False

    # ==================== Kline Methods ====================

    async def save_klines(
        self,
        symbol: str,
        timeframe: str,
        klines: List[Any],
        exchange_name: Optional[str] = None
    ) -> int:
        """
        批量保存K线数据（UPSERT）

        Args:
            symbol: 交易对符号
            timeframe: 时间周期 (1m, 5m, 15m, 1h, 4h, 1d等)
            klines: K线数据列表，每个元素是OHLCV对象
            exchange_name: 交易所名称

        Returns:
            成功保存的K线数量
        """
        if not klines:
            return 0

        try:
            exchange_id = await self._get_or_create_exchange_id(
                exchange_name or self.default_exchange_name
            )

            rows = [
                {
                    "exchange_id": exchange_id,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "timestamp": kline.timestamp,
                    "datetime": self._make_naive(kline.dt),
                    "open": kline.open,
                    "high": kline.high,
                    "low": kline.low,
                    "close": kline.close,
                    "volume": kline.volume,
                }
                for kline in klines
            ]

            stmt = insert(KlineModel).values(rows)
            stmt = stmt.on_conflict_do_update(
                index_elements=[
                    KlineModel.exchange_id,
                    KlineModel.symbol,
                    KlineModel.timeframe,
                    KlineModel.timestamp,
                ],
                set_={
                    "open": stmt.excluded.open,
                    "high": stmt.excluded.high,
                    "low": stmt.excluded.low,
                    "close": stmt.excluded.close,
                    "volume": stmt.excluded.volume,
                    "datetime": stmt.excluded.datetime,
                },
            )

            await self.session.execute(stmt)
            return len(rows)

        except Exception as e:
            self.logger.error(
                f"Failed to save klines for {symbol} {timeframe}: {e}",
                exc_info=True
            )
            return 0

    async def get_klines(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 200,
        exchange_name: Optional[str] = None
    ) -> List[KlineModel]:
        """
        获取K线数据

        Args:
            symbol: 交易对符号
            timeframe: 时间周期
            limit: 返回数量限制
            exchange_name: 交易所名称

        Returns:
            K线数据列表（按时间倒序）
        """
        try:
            query = select(KlineModel).where(
                and_(
                    KlineModel.symbol == symbol,
                    KlineModel.timeframe == timeframe
                )
            )

            if exchange_name:
                exchange_id = await self._get_or_create_exchange_id(exchange_name)
                query = query.where(KlineModel.exchange_id == exchange_id)

            query = query.order_by(desc(KlineModel.datetime)).limit(limit)

            result = await self.session.execute(query)
            return list(result.scalars().all())

        except Exception as e:
            self.logger.error(
                f"Failed to get klines for {symbol} {timeframe}: {e}"
            )
            return []

    # ==================== Query Methods ====================

    async def get_recent_trades(
        self,
        symbol: str,
        limit: int = 100,
        exchange_name: Optional[str] = None
    ) -> List[TradeModel]:
        """获取最近的成交记录"""
        try:
            query = select(TradeModel).where(TradeModel.symbol == symbol)

            if exchange_name:
                exchange_id = await self._get_or_create_exchange_id(exchange_name)
                query = query.where(TradeModel.exchange_id == exchange_id)

            query = query.order_by(desc(TradeModel.datetime)).limit(limit)

            result = await self.session.execute(query)
            return list(result.scalars().all())

        except Exception as e:
            self.logger.error(f"Failed to get recent trades: {e}")
            return []

    async def get_open_positions(
        self,
        exchange_name: Optional[str] = None,
        *,
        include_closed: bool = False,
    ) -> List[PositionModel]:
        """获取 positions 记录，默认仅返回 is_open=True 的持仓"""
        try:
            query = select(PositionModel)

            if not include_closed:
                query = query.where(PositionModel.is_open == True)  # pylint: disable=singleton-comparison

            if exchange_name:
                exchange_id = await self._get_or_create_exchange_id(exchange_name)
                query = query.where(PositionModel.exchange_id == exchange_id)

            result = await self.session.execute(query)
            return list(result.scalars().all())

        except Exception as e:
            self.logger.error(f"Failed to get open positions: {e}")
            return []

    async def get_portfolio_snapshots(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: Optional[int] = None,
        exchange_name: Optional[str] = None,
    ) -> List[PortfolioSnapshotModel]:
        """
        获取投资组合快照

        Args:
            start_date: 开始日期
            end_date: 结束日期
            limit: 返回数量限制（默认None=不限制）
                  当指定日期范围时，建议不设置limit以获取完整数据
                  当不指定日期范围时，建议设置limit防止返回过多数据

        Returns:
            快照列表
        """
        try:
            query = select(PortfolioSnapshotModel).order_by(desc(PortfolioSnapshotModel.datetime))

            filters = []
            if start_date:
                filters.append(PortfolioSnapshotModel.snapshot_date >= start_date)
            if end_date:
                filters.append(PortfolioSnapshotModel.snapshot_date <= end_date)

            if filters:
                query = query.where(and_(*filters))

            # 仅返回指定交易所的数据
            exchange_filter_name = exchange_name or self.default_exchange_name
            if exchange_filter_name:
                exchange_id = await self._get_or_create_exchange_id(exchange_filter_name)
                query = query.where(PortfolioSnapshotModel.exchange_id == exchange_id)

            # 只有明确指定limit时才应用限制
            if limit is not None:
                query = query.limit(limit)

            result = await self.session.execute(query)
            return list(result.scalars().all())

        except Exception as e:
            self.logger.error(f"Failed to get portfolio snapshots: {e}")
            return []

    async def get_performance_summary(self, days: int = 30) -> dict:
        """获取绩效摘要"""
        try:
            # 实现绩效统计逻辑
            # TODO: 完整实现
            return {}

        except Exception as e:
            self.logger.error(f"Failed to get performance summary: {e}")
            return {}

    # ==================== Closed Positions Methods ====================

    async def save_closed_position(
        self,
        position: PositionModel,
        exit_order_id: str,
        exit_price: Decimal,
        exit_time: datetime,
        fee: Decimal = Decimal('0'),
        close_reason: str = 'unknown'
    ) -> bool:
        """
        保存已平仓记录到 closed_positions 表

        Args:
            position: 要关闭的持仓记录
            exit_order_id: 平仓订单ID
            exit_price: 平仓价格
            exit_time: 平仓时间
            fee: 平仓手续费（默认0）
            close_reason: 平仓原因 (manual, stop_loss, take_profit, liquidation, system, unknown)
        """
        try:
            # 如果 exit_order_id 不在 orders 表中，置为 None 以避免外键冲突
            if exit_order_id:
                result = await self.session.execute(
                    select(OrderModel.id).where(OrderModel.id == exit_order_id)
                )
                if not result.scalar_one_or_none():
                    exit_order_id = None

            # 计算盈亏
            entry_value = position.entry_price * position.amount
            exit_value = exit_price * position.amount

            if position.side == 'buy':
                realized_pnl = exit_value - entry_value
            else:  # sell (做空)
                realized_pnl = entry_value - exit_value

            realized_pnl_percentage = (realized_pnl / entry_value * 100) if entry_value > 0 else Decimal("0")

            # 计算持仓时长
            if position.opened_at:
                try:
                    # 确保两个datetime都是naive或都是aware
                    opened_at = position.opened_at
                    if opened_at.tzinfo is not None:
                        # 如果 opened_at 有时区，移除时区信息
                        opened_at = opened_at.replace(tzinfo=None)

                    exit_time_normalized = exit_time
                    if exit_time.tzinfo is not None:
                        # 如果 exit_time 有时区，移除时区信息
                        exit_time_normalized = exit_time.replace(tzinfo=None)

                    holding_duration = int((exit_time_normalized - opened_at).total_seconds())

                    # 保护：如果持仓时间为负数，说明时间顺序有问题
                    if holding_duration < 0:
                        self.logger.error(
                            f"持仓时间为负数! opened_at={opened_at}, exit_time={exit_time_normalized}, "
                            f"duration={holding_duration}s. 将使用绝对值."
                        )
                        holding_duration = abs(holding_duration)

                except Exception as e:
                    self.logger.warning(f"计算持仓时长失败: {e}")
                    holding_duration = None
            else:
                holding_duration = None

            # 创建 closed_position 记录
            closed_position = ClosedPositionModel(
                exchange_id=position.exchange_id,
                symbol=position.symbol,
                side=position.side,
                entry_order_id=position.entry_order_id,
                entry_price=position.entry_price,
                entry_time=position.opened_at,
                exit_order_id=exit_order_id,
                exit_price=exit_price,
                exit_time=exit_time,
                amount=position.amount,
                entry_value=entry_value,
                exit_value=exit_value,
                realized_pnl=realized_pnl,
                realized_pnl_percentage=realized_pnl_percentage,
                total_fee=fee,  # 使用传入的手续费
                fee_currency="USDT",
                close_reason=close_reason,  # 使用传入的平仓原因
                holding_duration_seconds=holding_duration,
                leverage=position.leverage,
                created_at=datetime.now(timezone.utc).replace(tzinfo=None)
            )

            self.session.add(closed_position)
            await self.session.flush()

            self.logger.info(
                f"Saved closed position: {position.symbol} "
                f"PNL={realized_pnl:.2f} ({realized_pnl_percentage:.2f}%)"
            )
            return True

        except Exception as e:
            self.logger.error(f"Failed to save closed position: {e}")
            return False

    async def get_closed_positions(
        self,
        symbol: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: int = 100,
        exchange_name: Optional[str] = None
    ) -> List[ClosedPositionModel]:
        """
        查询已平仓记录

        Args:
            symbol: 交易对筛选
            start_date: 开始日期
            end_date: 结束日期
            limit: 返回记录数量限制
            exchange_name: 交易所名称
        """
        try:
            query = select(ClosedPositionModel).order_by(desc(ClosedPositionModel.exit_time))

            filters = []

            if exchange_name:
                exchange_id = await self._get_or_create_exchange_id(exchange_name)
                filters.append(ClosedPositionModel.exchange_id == exchange_id)

            if symbol:
                filters.append(ClosedPositionModel.symbol == symbol)

            if start_date:
                filters.append(ClosedPositionModel.exit_time >= datetime.combine(start_date, datetime.min.time()))

            if end_date:
                filters.append(ClosedPositionModel.exit_time <= datetime.combine(end_date, datetime.max.time()))

            if filters:
                query = query.where(and_(*filters))

            query = query.limit(limit)
            result = await self.session.execute(query)
            return list(result.scalars().all())

        except Exception as e:
            self.logger.error(f"Failed to get closed positions: {e}")
            return []

    # ==================== Performance Metrics Methods ====================

    async def get_performance_metrics(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        exchange_name: Optional[str] = None,
        limit: int = 100
    ) -> List['PerformanceMetricsModel']:
        """
        查询绩效指标记录

        Args:
            start_date: 开始日期
            end_date: 结束日期  
            exchange_name: 交易所名称
            limit: 返回记录数量限制
        """
        try:
            from src.services.database.models import PerformanceMetricsModel
            
            query = select(PerformanceMetricsModel).order_by(desc(PerformanceMetricsModel.start_date))

            filters = []

            if start_date:
                filters.append(PerformanceMetricsModel.start_date >= datetime.combine(start_date, datetime.min.time()))

            if end_date:
                filters.append(PerformanceMetricsModel.end_date <= datetime.combine(end_date, datetime.max.time()))

            if filters:
                query = query.where(and_(*filters))

            query = query.limit(limit)
            result = await self.session.execute(query)
            return list(result.scalars().all())

        except Exception as e:
            self.logger.error(f"Failed to get performance metrics: {e}")
            return []
