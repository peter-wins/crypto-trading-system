#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Account Synchronization Service

统一的账户同步服务，负责：
1. 定期从交易所同步账户信息（余额、持仓、订单）
2. 检测并处理交易所端的变化（手动平仓、止盈止损触发、强平等）
3. 更新本地数据库以保持一致性
4. 计算真实的盈亏（包括手续费）
5. 提供实时数据给 API 和决策系统
"""

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass

from src.core.logger import get_logger
from src.services.exchange import ExchangeService
from src.services.database import TradingDAO, PositionModel
from src.models.portfolio import Position, Portfolio
from src.models.trade import OrderSide

logger = get_logger(__name__)


@dataclass
class AccountSnapshot:
    """账户快照"""
    timestamp: datetime
    total_balance: Decimal
    available_balance: Decimal
    used_margin: Decimal
    unrealized_pnl: Decimal
    positions: List[Position]
    position_count: int
    total_position_value: Decimal

    def to_portfolio(self) -> Portfolio:
        """转换为 Portfolio 模型（用于归档快照）"""
        return Portfolio(
            timestamp=int(self.timestamp.timestamp() * 1000),
            dt=self.timestamp,
            wallet_balance=self.total_balance,
            available_balance=self.available_balance,
            margin_balance=self.used_margin,
            positions=self.positions,
            unrealized_pnl=self.unrealized_pnl,
            daily_pnl=Decimal("0"),
            total_return=Decimal("0"),
        )


@dataclass
class PositionChange:
    """持仓变化记录"""
    symbol: str
    side: str
    change_type: str  # 'closed', 'reduced', 'increased', 'liquidated'
    old_amount: Optional[Decimal]
    new_amount: Decimal
    exit_price: Optional[Decimal]
    exit_order_id: Optional[str]
    exit_time: datetime
    reason: str  # 'manual', 'stop_loss', 'take_profit', 'liquidation', 'system'


@dataclass
class ExpectedClosure:
    """TradingExecutor 预登记的平仓信息"""
    symbol: str
    side: str
    amount: Decimal
    exit_price: Decimal
    exit_time: datetime
    order_id: Optional[str]
    reason: str


class AccountSyncService:
    """
    账户同步服务

    功能：
    1. 定期同步账户数据
    2. 检测持仓变化
    3. 更新数据库
    4. 计算精确盈亏
    """

    def __init__(
        self,
        exchange_service: ExchangeService,
        db_manager,  # DatabaseManager
        sync_interval: int = 10,  # 同步间隔（秒）
        db_exchange_name: Optional[str] = None,
    ):
        self.exchange_service = exchange_service
        self.db_manager = db_manager
        self.sync_interval = sync_interval
        self.exchange_name = exchange_service.exchange_name  # 实际交易所（用于API）
        self.db_exchange_name = (db_exchange_name or "binance").lower()

        # 上次同步的快照
        self.last_snapshot: Optional[AccountSnapshot] = None

        # 后台任务
        self._sync_task: Optional[asyncio.Task] = None
        self._running = False
        self._sync_lock = asyncio.Lock()

        # 统计
        self.sync_count = 0
        self.error_count = 0
        self.last_sync_time: Optional[datetime] = None

        # 注册的预期平仓，用于TradingExecutor退出后即时落库
        self._expected_closures: Dict[Tuple[str, str], ExpectedClosure] = {}
        self._entry_fee_lookback_ms = 10 * 60 * 1000  # 10分钟

    async def start(self):
        """启动同步服务"""
        if self._running:
            logger.warning("账户同步服务已在运行")
            return

        self._running = True
        self._sync_task = asyncio.create_task(self._sync_loop())
        logger.info(f"✓ [账户同步] 服务已启动 (间隔: {self.sync_interval}秒)")

    async def stop(self):
        """停止同步服务"""
        self._running = False
        if self._sync_task:
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass
        logger.info("账户同步服务已停止")

    def register_expected_close(
        self,
        symbol: str,
        side: OrderSide | str,
        amount: Decimal,
        *,
        exit_price: Decimal,
        exit_time: datetime,
        order_id: Optional[str],
        reason: str = "system",
    ) -> None:
        """登记TradingExecutor预期的平仓结果，供下一次同步使用"""
        normalized_side = self._normalize_side_value(side)
        key = (symbol, normalized_side)
        self._expected_closures[key] = ExpectedClosure(
            symbol=symbol,
            side=normalized_side,
            amount=amount,
            exit_price=exit_price,
            exit_time=exit_time,
            order_id=order_id,
            reason=reason,
        )
        logger.debug(
            "登记预期平仓: %s %s amount=%s price=%s",
            symbol, normalized_side, amount, exit_price
        )

    async def _sync_loop(self):
        """同步循环"""
        while self._running:
            try:
                await self.sync_now()
                await asyncio.sleep(self.sync_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.error_count += 1
                logger.error(f"账户同步失败: {e}", exc_info=True)
                await asyncio.sleep(self.sync_interval)

    async def sync_now(self) -> AccountSnapshot:
        """
        立即执行一次同步

        Returns:
            账户快照
        """
        async with self._sync_lock:
            try:
                # 1. 获取交易所数据
                exchange_data = await self._fetch_exchange_data()

                # 2. 创建快照
                snapshot = await self._create_snapshot(exchange_data)

                # 3. 检测变化
                if self.last_snapshot:
                    changes = await self._detect_changes(self.last_snapshot, snapshot)
                    if changes:
                        await self._process_changes(changes, exchange_data)

                # 4. 更新数据库
                await self._update_database(snapshot, exchange_data)

                # 5. 保存快照
                self.last_snapshot = snapshot
                self.sync_count += 1
                self.last_sync_time = datetime.now(timezone.utc)

                # 只在每10次同步输出一次简洁信息
                if self.sync_count % 10 == 1:
                    logger.info(
                        f"账户: {snapshot.total_balance:.2f} USDT | "
                        f"{snapshot.position_count} 个持仓 | "
                        f"盈亏: {snapshot.unrealized_pnl:+.2f}"
                    )

                return snapshot

            except Exception as e:
                logger.error(f"账户同步失败: {e}", exc_info=True)
                raise

    async def _fetch_exchange_data(self) -> Dict:
        """从交易所获取完整数据"""
        # 并行获取数据以提高效率
        balance_task = self.exchange_service.fetch_balance()
        positions_task = self.exchange_service.fetch_positions()

        balance, positions = await asyncio.gather(balance_task, positions_task)

        # 获取每个持仓的未完成订单（可能包含止盈止损）
        open_orders: Dict[str, List[Dict]] = {}
        symbols = [pos.get('symbol') for pos in positions if pos.get('symbol')]
        unique_symbols = list(dict.fromkeys(symbols))
        if unique_symbols:
            tasks = [
                self.exchange_service.fetch_open_orders(symbol)
                for symbol in unique_symbols
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for symbol, result in zip(unique_symbols, results):
                if isinstance(result, Exception):
                    logger.debug("获取 %s 未完成订单失败: %s", symbol, result)
                    open_orders[symbol] = []
                else:
                    open_orders[symbol] = result

        return {
            'balance': balance,
            'positions': positions,
            'open_orders': open_orders,
            'timestamp': datetime.now(timezone.utc)
        }

    async def _create_snapshot(self, exchange_data: Dict) -> AccountSnapshot:
        """创建账户快照"""
        balance = exchange_data['balance']
        positions = exchange_data['positions']
        open_orders = exchange_data['open_orders']

        # 构建保护单映射 (symbol, side) -> {stop_loss, take_profit}
        protection_map = self._build_protection_map(open_orders)

        # 转换为 Position 对象
        position_list = []
        total_position_value = Decimal('0')

        # 只记录持仓数量,不记录详细信息
        if len(positions) > 0:
            logger.debug(f"同步账户: {len(positions)} 个持仓")

        for pos_data in positions:
            # 币安合约API使用 positionAmt 字段而不是 contracts
            # CCXT可能统一为 contracts,但我们检查两个字段以防万一
            contracts = pos_data.get('contracts') or pos_data.get('positionAmt') or 0
            contracts = float(contracts)

            # 跳过零持仓
            if abs(contracts) < 0.0001:
                continue

            symbol = pos_data['symbol']
            amount = abs(Decimal(str(pos_data.get('contracts', 0))))
            entry_price = Decimal(str(pos_data.get('entryPrice', 0)))
            current_price = Decimal(str(pos_data.get('markPrice', 0)))
            unrealized_pnl = Decimal(str(pos_data.get('unrealizedPnl', 0)))

            # 计算持仓价值
            value = amount * current_price

            # 计算未实现盈亏百分比
            cost = entry_price * amount
            unrealized_pnl_percentage = (unrealized_pnl / cost * Decimal('100')) if cost > 0 else Decimal('0')

            # 确定持仓方向
            # 在 HEDGE 模式下，Binance 返回 positionSide 字段 ('LONG', 'SHORT', 'BOTH')
            # 在 ONE_WAY 模式下，根据 contracts 正负判断
            position_side = pos_data.get('side') or pos_data.get('info', {}).get('positionSide')

            if position_side:
                # HEDGE 模式：使用 positionSide 字段
                # LONG -> buy, SHORT -> sell
                side = 'buy' if position_side.upper() in ['LONG', 'BUY'] else 'sell'
            else:
                # ONE_WAY 模式：根据 contracts 正负判断
                side = 'buy' if float(pos_data.get('contracts', 0)) > 0 else 'sell'

            # 从保护单映射获取止盈止损
            protection_key = (symbol, side)
            protection = protection_map.get(protection_key, {})

            # 提取杠杆倍数（确保转换为int）
            # 优先从 API 直接获取,如果没有则通过持仓价值和保证金计算
            leverage_raw = pos_data.get('leverage')
            if leverage_raw is None:
                # 尝试从 info 字段获取
                info = pos_data.get('info', {})
                leverage_raw = info.get('leverage')

            leverage = None
            if leverage_raw:
                try:
                    leverage = int(leverage_raw)
                except (ValueError, TypeError):
                    logger.warning(f"{symbol} 杠杆倍数解析失败: {leverage_raw}")
            else:
                # 通过持仓价值和保证金计算杠杆
                # leverage = notional / initial_margin
                try:
                    notional = abs(float(pos_data.get('notional', 0)))
                    initial_margin = float(pos_data.get('initialMargin', 0))

                    if initial_margin > 0 and notional > 0:
                        calculated_leverage = round(notional / initial_margin)
                        leverage = int(calculated_leverage)
                except (ValueError, TypeError, KeyError):
                    pass

            # 提取开仓时间（Binance: updateTime）
            # CCXT可能在顶层或info字段中
            opened_at_raw = pos_data.get('timestamp') or pos_data.get('info', {}).get('updateTime')
            opened_at = None
            if opened_at_raw:
                try:
                    # Binance返回的是毫秒时间戳
                    opened_at = int(opened_at_raw)
                except (ValueError, TypeError):
                    pass

            position = Position(
                symbol=symbol,
                side=side,
                amount=amount,
                entry_price=entry_price,
                current_price=current_price,
                unrealized_pnl=unrealized_pnl,
                unrealized_pnl_percentage=unrealized_pnl_percentage,
                value=value,
                leverage=leverage,
                liquidation_price=Decimal(str(pos_data.get('liquidationPrice', 0))) if pos_data.get('liquidationPrice') else None,
                stop_loss=protection.get('stop_loss'),
                take_profit=protection.get('take_profit'),
                opened_at=opened_at,
            )
            position_list.append(position)
            total_position_value += value

        # 从币安原始 API 数据中提取正确的余额字段
        # 注意：CCXT 的 balance.total 实际上是 totalMarginBalance（保证金余额），不是钱包余额
        info = balance.get('info', {})
        wallet_balance = Decimal(str(info.get('totalWalletBalance', 0)))  # 钱包余额（总资产）
        available_balance = Decimal(str(info.get('availableBalance', 0)))  # 可用余额（可下单余额）

        # 使用占用保证金：优先 totalInitialMargin，缺省时由 "钱包-可用" 推导
        used_margin = info.get('totalInitialMargin')
        if used_margin is None:
            used_margin = wallet_balance - available_balance
        else:
            used_margin = Decimal(str(used_margin))

        if used_margin < Decimal('0'):
            used_margin = Decimal('0')

        return AccountSnapshot(
            timestamp=exchange_data['timestamp'],
            total_balance=wallet_balance,  # 使用钱包余额作为总资产
            available_balance=available_balance,
            used_margin=used_margin,  # 已占用保证金
            unrealized_pnl=sum((p.unrealized_pnl for p in position_list), Decimal('0')),
            positions=position_list,
            position_count=len(position_list),
            total_position_value=total_position_value,
        )

    def _build_protection_map(self, open_orders: Dict[str, List]) -> Dict:
        """
        构建保护单映射

        Args:
            open_orders: {symbol: [order1, order2, ...]}

        Returns:
            {(symbol, side): {'stop_loss': Decimal, 'take_profit': Decimal}}
        """
        protection_map = {}

        for symbol, orders in open_orders.items():
            for order in orders:
                try:
                    order_type = (order.get('type') or '').lower()

                    # 只处理止盈止损订单
                    if order_type not in {
                        'stop',
                        'stop_loss',
                        'stop_market',
                        'take_profit',
                        'take_profit_market',
                        'take_profit_limit',
                    }:
                        continue

                    # 检查是否是平仓单
                    reduce_only = bool(order.get('reduceOnly'))
                    info = order.get('info', {}) or {}
                    close_position_flag = str(info.get('closePosition', '')).lower() == 'true'

                    if not (reduce_only or close_position_flag):
                        continue

                    # 获取触发价格
                    stop_price_raw = (
                        order.get('stopPrice') or
                        order.get('price') or
                        info.get('stopPrice')
                    )

                    if not stop_price_raw or str(stop_price_raw) in {'0', '0.0'}:
                        continue

                    price = Decimal(str(stop_price_raw))

                    # 平仓单方向与持仓方向相反
                    # 平多仓(sell)对应 buy 持仓，平空仓(buy)对应 sell 持仓
                    side_raw = (order.get('side') or '').lower()
                    if side_raw == 'sell':
                        target_side = 'buy'  # 这个止盈止损是给 buy 持仓用的
                    elif side_raw == 'buy':
                        target_side = 'sell'  # 这个止盈止损是给 sell 持仓用的
                    else:
                        continue

                    key = (symbol, target_side)
                    protection = protection_map.setdefault(key, {})

                    # 根据订单类型设置止盈或止损
                    if order_type in {'stop', 'stop_loss', 'stop_market'}:
                        protection['stop_loss'] = price
                    else:
                        protection['take_profit'] = price

                except Exception as e:
                    logger.debug(f"解析保护单失败 {symbol}: {e}")
                    continue

        return protection_map

    async def _detect_changes(
        self,
        old_snapshot: AccountSnapshot,
        new_snapshot: AccountSnapshot
    ) -> List[PositionChange]:
        """检测持仓变化"""
        changes = []

        # 创建持仓映射 (symbol, side)
        old_positions = {
            (p.symbol, self._position_side(p)): p
            for p in old_snapshot.positions
        }
        new_positions = {
            (p.symbol, self._position_side(p)): p
            for p in new_snapshot.positions
        }

        # 检查每个旧持仓
        for (symbol, side), old_pos in old_positions.items():
            new_pos = new_positions.get((symbol, side))
            if not new_pos:
                # 持仓完全关闭
                changes.append(PositionChange(
                    symbol=symbol,
                    side=side,
                    change_type='closed',
                    old_amount=old_pos.amount,
                    new_amount=Decimal('0'),
                    exit_price=old_pos.current_price,  # 使用最新价格作为近似
                    exit_order_id=None,
                    exit_time=new_snapshot.timestamp,
                    reason='unknown'  # 需要进一步查询确定原因
                ))
            elif abs(new_pos.amount - old_pos.amount) > Decimal('0.0001'):
                # 持仓数量变化
                if new_pos.amount < old_pos.amount:
                    changes.append(PositionChange(
                        symbol=symbol,
                        side=side,
                        change_type='reduced',
                        old_amount=old_pos.amount,
                        new_amount=new_pos.amount,
                        exit_price=new_pos.current_price,
                        exit_order_id=None,
                        exit_time=new_snapshot.timestamp,
                        reason='unknown'
                    ))
                else:
                    changes.append(PositionChange(
                        symbol=symbol,
                        side=side,
                        change_type='increased',
                        old_amount=old_pos.amount,
                        new_amount=new_pos.amount,
                        exit_price=None,
                        exit_order_id=None,
                        exit_time=new_snapshot.timestamp,
                        reason='unknown'
                    ))

        return changes

    async def _process_changes(self, changes: List[PositionChange], exchange_data: Dict):
        """处理持仓变化"""
        for change in changes:
            try:
                if change.change_type in ['closed', 'reduced']:
                    if self._apply_expected_closure(change):
                        await self._save_position_close(change, fee=Decimal('0'))
                        continue
                    # 查询最近的成交记录以获取精确价格
                    await self._process_position_close(change, exchange_data)
                elif change.change_type == 'increased':
                    # 记录加仓
                    logger.info(f"检测到 {change.symbol} 加仓: {change.old_amount} -> {change.new_amount}")

            except Exception as e:
                logger.error(f"处理持仓变化失败 {change.symbol}: {e}")

    async def _process_position_close(self, change: PositionChange, exchange_data: Dict):
        """
        处理持仓平仓，优先基于真实成交记录计算出场价格与手续费
        """
        symbol = change.symbol

        try:
            since_time = self.last_snapshot.timestamp if self.last_snapshot else None
            summary = await self._summarize_close_trades(
                symbol=symbol,
                position_side=change.side,
                since_time=since_time,
            )

            if summary:
                change.exit_price = summary["avg_price"]
                change.exit_order_id = summary["order_id"]
                change.reason = summary["reason"]
                exit_dt = summary["exit_time"]
                if exit_dt:
                    change.exit_time = exit_dt.replace(tzinfo=None)

                logger.info(
                    f"检测到 {symbol} 平仓: "
                    f"数量={summary['total_amount']} "
                    f"均价={summary['avg_price']:.4f} "
                    f"手续费={summary['total_fee']:.4f} "
                    f"原因={summary['reason']}"
                )

                await self._save_position_close(change, summary["total_fee"])
            else:
                logger.warning(f"{symbol} 未找到平仓成交记录，使用市场价格")
                change.exit_time = datetime.now(timezone.utc).replace(tzinfo=None)
                await self._save_position_close(change, Decimal('0'))

        except Exception as e:
            logger.error(f"查询 {symbol} 成交记录失败: {e}")

    def _apply_expected_closure(self, change: PositionChange) -> bool:
        """如果TradingExecutor已登记平仓，直接使用登记信息"""
        key = (change.symbol, change.side)
        expected = self._expected_closures.pop(key, None)
        if not expected:
            return False

        change.exit_price = expected.exit_price
        change.exit_time = expected.exit_time
        change.exit_order_id = expected.order_id
        change.reason = expected.reason
        logger.debug(
            "使用预登记平仓: %s %s price=%s",
            change.symbol, change.side, change.exit_price
        )
        return True

    def _determine_close_reason(self, trades: List[Dict]) -> str:
        """确定平仓原因"""
        # 检查订单类型
        for trade in trades:
            order_type = trade.get('type')
            if not order_type:
                continue
            order_type = str(order_type).lower()
            if 'stop' in order_type:
                return 'stop_loss'
            elif 'take_profit' in order_type or 'limit' in order_type:
                return 'take_profit'
            elif 'liquidation' in order_type:
                return 'liquidation'

        # 检查是否是手动平仓（通过 API 或网页）
        return 'manual'

    async def _summarize_close_trades(
        self,
        symbol: str,
        position_side: str,
        since_time: Optional[datetime],
    ) -> Optional[Dict[str, Any]]:
        """从交易所成交记录中提取平仓摘要"""
        try:
            trades = await self.exchange_service.fetch_my_trades(symbol=symbol, limit=50)
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning(f"{symbol} 获取成交记录失败: {exc}")
            return None

        if not trades:
            return None

        close_trades: List[Dict] = []
        total_amount = Decimal('0')
        total_value = Decimal('0')
        total_fee = Decimal('0')

        for trade in reversed(trades):
            trade_time = datetime.fromtimestamp(trade.get('timestamp', 0) / 1000, tz=timezone.utc)
            if since_time and trade_time <= since_time:
                continue

            trade_side = (trade.get('side') or '').lower()
            if not trade_side:
                continue

            if position_side == 'buy' and trade_side != 'sell':
                continue
            if position_side == 'sell' and trade_side != 'buy':
                continue

            amount = Decimal(str(trade.get('amount', 0)))
            price = Decimal(str(trade.get('price', 0)))
            fee = Decimal(str(trade.get('fee', {}).get('cost', 0) or 0))

            if amount <= 0:
                continue

            close_trades.append(trade)
            total_amount += amount
            total_value += amount * price
            total_fee += fee

        if not close_trades or total_amount <= Decimal('0'):
            return None

        avg_price = total_value / total_amount
        reason = self._determine_close_reason(close_trades)
        order_id = close_trades[0].get('order')

        last_trade_time = datetime.fromtimestamp(close_trades[-1].get('timestamp', 0) / 1000, tz=timezone.utc)

        return {
            "avg_price": avg_price,
            "total_amount": total_amount,
            "total_fee": total_fee,
            "reason": reason,
            "order_id": order_id,
            "exit_time": last_trade_time,
        }

    def _normalize_side_value(self, side: OrderSide | str | None) -> str:
        """统一side值到 buy/sell"""
        if isinstance(side, OrderSide):
            return side.value
        if isinstance(side, str):
            side_lower = side.lower()
            if side_lower in ("buy", "sell"):
                return side_lower
            if side_lower in ("long", "short"):
                return "buy" if side_lower == "long" else "sell"
        return "buy"

    def _position_side(self, position: Position) -> str:
        """从 Position 对象提取 buy/sell 方向"""
        side = position.side
        if isinstance(side, OrderSide):
            return side.value
        if isinstance(side, str):
            return self._normalize_side_value(side)
        return "buy" if position.amount >= Decimal("0") else "sell"

    async def _save_position_close(self, change: PositionChange, fee: Decimal):
        """保存平仓记录到数据库"""
        from src.services.database import TradingDAO

        async with self.db_manager.get_session() as session:
            dao = TradingDAO(session)

            position = await dao.get_position_by_symbol_side(
                change.symbol,
                change.side,
                exchange_name=self.db_exchange_name,
            )

            if not position:
                logger.warning(f"未找到 {change.symbol} {change.side} 的持仓记录")
                return

            entry_fee_total = Decimal(str(getattr(position, "entry_fee", 0) or 0))
            fee_to_use = fee

            old_amount = change.old_amount or Decimal(str(getattr(position, "amount", 0) or 0))
            new_amount = change.new_amount if change.new_amount is not None else Decimal('0')

            if entry_fee_total > 0 and old_amount > Decimal('0'):
                closed_amount = max(old_amount - new_amount, Decimal('0'))
                if closed_amount <= Decimal('0'):
                    closed_amount = old_amount
                ratio = min(closed_amount / old_amount, Decimal('1'))
                entry_fee_used = (entry_fee_total * ratio).quantize(Decimal('0.00000001'))
                fee_to_use = fee + entry_fee_used

                if change.change_type == 'closed':
                    position.entry_fee = Decimal('0')
                else:
                    position.entry_fee = max(entry_fee_total - entry_fee_used, Decimal('0'))
            else:
                if change.change_type == 'closed':
                    position.entry_fee = Decimal('0')

            # 保存到 closed_positions 表
            await dao.save_closed_position(
                position=position,
                exit_order_id=change.exit_order_id,
                exit_price=change.exit_price,
                exit_time=change.exit_time,
                fee=fee_to_use,
                close_reason=change.reason
            )

            # 如果是完全平仓，删除持仓记录
            if change.change_type == 'closed':
                await session.delete(position)
            else:
                # 部分平仓，更新持仓数量
                position.amount = change.new_amount

            await session.commit()

    async def _update_database(self, snapshot: AccountSnapshot, exchange_data: Dict):
        """更新数据库中的持仓信息和账户快照"""
        from src.services.database import TradingDAO

        async with self.db_manager.get_session() as session:
            dao = TradingDAO(session)

            # 获取所有开放持仓
            all_db_positions = await dao.get_open_positions(
                exchange_name=self.db_exchange_name
            )

            # 创建 (symbol, side) -> db_position 的映射
            # 支持双向持仓：同一symbol可以有多仓(buy)和空仓(sell)
            db_pos_map = {(p.symbol, p.side): p for p in all_db_positions}

            # 同步持仓：更新已存在的，创建新的
            for position in snapshot.positions:
                side = self._position_side(position)
                db_pos = db_pos_map.get((position.symbol, side))
                if db_pos:
                    # 更新已存在的持仓
                    db_pos.entry_price = position.entry_price
                    db_pos.current_price = position.current_price
                    db_pos.unrealized_pnl = position.unrealized_pnl
                    db_pos.amount = position.amount  # 也更新数量，防止部分平仓后不一致
                    db_pos.leverage = position.leverage  # 更新杠杆倍数
                    db_pos.value = position.value
                    db_pos.liquidation_price = position.liquidation_price
                    db_pos.stop_loss = position.stop_loss
                    db_pos.take_profit = position.take_profit

                    # 更新开仓时间（如果之前为空）
                    # position.opened_at 是毫秒时间戳(int)，需要转换为 datetime
                    if position.opened_at and not db_pos.opened_at:
                        from datetime import datetime as dt
                        try:
                            # 将毫秒时间戳转换为 datetime
                            db_pos.opened_at = dt.fromtimestamp(position.opened_at / 1000.0)
                        except (ValueError, TypeError, OSError):
                            pass

                    db_pos.updated_at = datetime.now()  # 使用 naive datetime
                else:
                    # 创建新持仓（交易所有但数据库没有）
                    if getattr(position, "entry_fee", None) is None:
                        position.entry_fee = await self._estimate_entry_fee(position)
                    success = await dao.save_position(
                        position=position,
                        exchange_name=self.db_exchange_name
                    )
                    if success:
                        logger.info(f"✓ 同步新持仓到数据库: {position.symbol} {position.side.value} {position.amount}")
                    else:
                        logger.warning(f"✗ 同步新持仓失败: {position.symbol}")

            # 关闭已平仓的持仓（数据库有但交易所没有）
            # 在 HEDGE 模式下，必须使用 (symbol, side) 元组来准确识别持仓
            current_positions = {
                (p.symbol, self._position_side(p)) for p in snapshot.positions
            }
            for db_pos in all_db_positions:
                if (db_pos.symbol, db_pos.side) not in current_positions:
                    # 交易所已无此持仓，需要记录平仓并删除持仓记录
                    logger.info(f"检测到已平仓: {db_pos.symbol} {db_pos.side}, 创建平仓记录并删除持仓")

                    # 1. 创建 closed_position 记录
                    try:
                        since_time = db_pos.updated_at or db_pos.opened_at
                        if since_time and since_time.tzinfo is None:
                            since_time = since_time.replace(tzinfo=timezone.utc)

                        summary = await self._summarize_close_trades(
                            symbol=db_pos.symbol,
                            position_side=db_pos.side,
                            since_time=since_time,
                        )

                        entry_fee_total = Decimal(str(getattr(db_pos, "entry_fee", 0) or 0))

                        if summary:
                            exit_price = summary["avg_price"]
                            fee = summary["total_fee"] + entry_fee_total
                            exit_order_id = summary["order_id"]
                            close_reason = summary["reason"]
                            exit_time = summary["exit_time"].replace(tzinfo=None) if summary["exit_time"] else datetime.now(timezone.utc).replace(tzinfo=None)
                        else:
                            exit_price = Decimal(str(db_pos.current_price)) if db_pos.current_price else Decimal('0')
                            fee = entry_fee_total
                            exit_order_id = None
                            close_reason = 'system'
                            exit_time = datetime.now(timezone.utc).replace(tzinfo=None)

                        await dao.save_closed_position(
                            position=db_pos,
                            exit_order_id=exit_order_id,
                            exit_price=exit_price,
                            exit_time=exit_time,
                            fee=fee,
                            close_reason=close_reason
                        )
                        logger.info(f"✓ 已创建平仓记录: {db_pos.symbol} {db_pos.side}")
                    except Exception as e:
                        logger.error(f"✗ 创建平仓记录失败: {db_pos.symbol} {db_pos.side}, {e}")

                    # 2. 删除 positions 表中的记录
                    await session.delete(db_pos)
                    logger.info(f"✓ 已删除持仓记录: {db_pos.symbol} {db_pos.side}")

            # 更新最新的账户快照（不新增记录，只更新最新一条）
            await dao.update_latest_portfolio_snapshot(
                wallet_balance=float(snapshot.total_balance),
                available_balance=float(snapshot.available_balance),
                margin_balance=float(snapshot.used_margin),
                unrealized_pnl=float(snapshot.unrealized_pnl),
                positions=snapshot.positions,
                exchange_name=self.db_exchange_name
            )

            since_last_archive = None
            if self.last_snapshot:
                since_last_archive = (self.last_snapshot.timestamp - snapshot.timestamp).total_seconds() if isinstance(self.last_snapshot.timestamp, datetime) else None

            if not hasattr(self, "_last_archive_time"):
                self._last_archive_time = None
            need_archive = False
            reason = None

            if self._last_archive_time is None:
                need_archive = True
                reason = "initial"
            else:
                time_since = (datetime.now(timezone.utc) - self._last_archive_time).total_seconds()
                if time_since >= 3600:
                    need_archive = True
                    reason = "hourly"

            if self.last_snapshot and snapshot.position_count != self.last_snapshot.position_count:
                need_archive = True
                reason = "position_change"

            if need_archive:
                await dao.save_portfolio_snapshot(
                    portfolio=snapshot.to_portfolio(),
                    exchange_name=self.db_exchange_name,
                    archive_reason=reason,
                    is_archive=True,
                    position_count=snapshot.position_count,
                )
                self._last_archive_time = datetime.now(timezone.utc)

            await session.commit()

    async def get_current_snapshot(self) -> Optional[AccountSnapshot]:
        """获取当前账户快照（不执行同步）"""
        return self.last_snapshot

    async def force_sync(self) -> AccountSnapshot:
        """强制立即同步"""
        logger.info("强制执行账户同步...")
        return await self.sync_now()

    def get_stats(self) -> Dict:
        """获取同步服务统计信息"""
        return {
            'sync_count': self.sync_count,
            'error_count': self.error_count,
            'last_sync_time': self.last_sync_time.isoformat() if self.last_sync_time else None,
            'is_running': self._running,
            'sync_interval': self.sync_interval,
        }

    async def _estimate_entry_fee(self, position: Position) -> Decimal:
        """估算开仓手续费"""
        try:
            amount_target = position.amount
            if not amount_target or amount_target <= Decimal('0'):
                return Decimal('0')

            since_ms = None
            if position.opened_at:
                since_ms = max(int(position.opened_at) - self._entry_fee_lookback_ms, 0)

            trades = await self.exchange_service.fetch_my_trades(
                symbol=position.symbol,
                since=since_ms,
                limit=200
            )

            if not trades:
                return Decimal('0')

            target_side = self._position_side(position)
            trades_sorted = sorted(trades, key=lambda t: t.get('timestamp') or 0)
            accumulated = Decimal('0')
            fee_total = Decimal('0')

            for trade in trades_sorted:
                trade_side = (trade.get('side') or '').lower()
                if trade_side != target_side:
                    continue
                amount = Decimal(str(trade.get('amount', 0)))
                if amount <= 0:
                    continue
                fee = Decimal(str(trade.get('fee', {}).get('cost', 0) or 0))
                accumulated += amount
                fee_total += fee
                if accumulated >= amount_target:
                    break

            return fee_total

        except Exception as exc:  # pylint: disable=broad-except
            logger.debug("估算开仓手续费失败 %s: %s", position.symbol, exc)
            return Decimal('0')
