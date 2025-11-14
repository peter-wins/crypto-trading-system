"""
投资组合管理模块

负责同步交易所仓位、计算组合指标，并在纸面交易模式下维护本地状态。
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple, Set

import ccxt.async_support as ccxt  # type: ignore

from src.core.exceptions import PortfolioSyncError, TradingSystemError
from src.core.logger import get_logger
from src.services.exchange import get_exchange_service
from src.models.performance import PerformanceMetrics
from src.models.portfolio import Portfolio
from src.models.trade import OrderSide, Position


logger = get_logger(__name__)

BINANCE_USDM_TESTNET_API: Dict[str, str] = {
    "dapiPublic": "https://testnet.binancefuture.com/dapi/v1",
    "dapiPrivate": "https://testnet.binancefuture.com/dapi/v1",
    "dapiPrivateV2": "https://testnet.binancefuture.com/dapi/v2",
    "fapiPublic": "https://testnet.binancefuture.com/fapi/v1",
    "fapiPublicV2": "https://testnet.binancefuture.com/fapi/v2",
    "fapiPublicV3": "https://testnet.binancefuture.com/fapi/v3",
    "fapiPrivate": "https://testnet.binancefuture.com/fapi/v1",
    "fapiPrivateV2": "https://testnet.binancefuture.com/fapi/v2",
    "fapiPrivateV3": "https://testnet.binancefuture.com/fapi/v3",
    "public": "https://testnet.binance.vision/api/v3",
    "private": "https://testnet.binance.vision/api/v3",
    "v1": "https://testnet.binance.vision/api/v1",
}


class PortfolioManager:
    """
    投资组合管理器。

    支持两种模式：
    1. 真实模式：通过 CCXT 同步交易所仓位与余额。
    2. 纸面模式：维护内存状态，适用于模拟交易或测试。
    """

    def __init__(
        self,
        exchange_id: str = "binance",
        config: Optional[Dict[str, Any]] = None,
        *,
        paper_trading: bool = False,
        base_currency: str = "USDT",
        initial_portfolio: Optional[Portfolio] = None,
        sync_interval_seconds: int = 300,  # 默认5分钟同步一次
        db_manager=None,  # DatabaseManager for reading synced data
        account_sync_service=None,  # AccountSyncService for force sync
    ) -> None:
        self.exchange_id = exchange_id
        self.config = config or {}
        self.paper_trading = paper_trading
        self.base_currency = base_currency
        self.sync_interval_seconds = sync_interval_seconds
        self.db_manager = db_manager
        self.account_sync_service = account_sync_service
        # Note: 不再需要 self._exchange，改用全局 ExchangeService
        self._sync_lock = asyncio.Lock()  # 用于同步持仓的锁
        self._portfolio_cache: Optional[Portfolio] = initial_portfolio
        self._positions: Dict[str, Position] = {}
        self._last_sync_time: float = 0  # 上次同步时间戳
        self._sync_debounce_seconds: float = 2.0  # 去重窗口:2秒内的重复同步请求将被忽略
        if initial_portfolio:
            self._portfolio_cache = initial_portfolio
            self._positions = {pos.symbol: pos for pos in initial_portfolio.positions}

    # ------------------------------------------------------------------ #
    # public API
    # ------------------------------------------------------------------ #

    async def get_current_portfolio(self, force_sync: bool = False) -> Portfolio:
        """
        获取当前组合。

        同步策略：
        - 纸面模式：总是使用缓存
        - 真实模式：
          1. 如果 force_sync=True，通过 AccountSyncService 强制同步交易所
          2. 否则从数据库读取 AccountSyncService 自动同步的数据（每10秒）
          3. 如果数据库不可用，回退到直接调用交易所

        Args:
            force_sync: 是否强制立即同步（订单执行后应设为True）
        """
        if self.paper_trading:
            if not self._portfolio_cache:
                self._portfolio_cache = self._build_portfolio_from_positions()
            logger.debug("纸面模式：使用缓存组合 (总值: %s USDT)", self._portfolio_cache.total_value)
            return self._portfolio_cache

        # 真实交易模式：优先使用 AccountSyncService
        logger.debug(f"检查服务可用性: account_sync_service={self.account_sync_service is not None}, db_manager={self.db_manager is not None}")
        if self.account_sync_service and self.db_manager:
            try:
                if force_sync:
                    # 强制同步：触发 AccountSyncService 立即同步
                    logger.info("通过 AccountSyncService 强制同步账户...")
                    snapshot = await self.account_sync_service.force_sync()
                    portfolio = self._convert_snapshot_to_portfolio(snapshot)
                    logger.info(
                        "✓ 强制同步完成 | 余额: %s USDT | 持仓数: %d",
                        portfolio.cash,
                        len(portfolio.positions),
                    )
                    return portfolio
                else:
                    # 从数据库读取最新数据（由 AccountSyncService 每10秒自动同步）
                    portfolio = await self._fetch_portfolio_from_database()
                    if portfolio:
                        logger.debug(
                            "从数据库读取账户数据 (由 AccountSyncService 同步) | 余额: %.2f USDT | 持仓: %d",
                            portfolio.wallet_balance,
                            len(portfolio.positions),
                        )
                        return portfolio
                    else:
                        logger.info("数据库暂无账户数据（首次启动），通过 AccountSyncService 强制同步...")
                        # 首次运行时，使用 AccountSyncService 强制同步一次
                        import asyncio
                        snapshot = await self.account_sync_service.force_sync()
                        portfolio = self._convert_snapshot_to_portfolio(snapshot)
                        logger.info(
                            "✓ 首次同步完成 | 余额: %s USDT | 持仓数: %d",
                            portfolio.cash,
                            len(portfolio.positions),
                        )
                        return portfolio

            except Exception as e:
                logger.warning(f"使用 AccountSyncService 失败: {e}，回退到直接同步交易所", exc_info=True)
                return await self._fetch_portfolio_from_exchange_fallback()

        # 回退：如果没有 AccountSyncService，使用原来的逻辑
        logger.warning("AccountSyncService 未配置，使用回退逻辑")
        return await self._fetch_portfolio_from_exchange_fallback()

    async def update_portfolio(self) -> Portfolio:
        """
        更新投资组合（通常在订单执行后调用）。

        策略：
        - 订单执行后必须立即同步交易所数据，以获取最新持仓
        - 虽然会触发 API 调用，但这是必要的（订单执行本身就很少发生）
        - 确保 _save_snapshots 能获取到正确的持仓数据
        """
        if self.paper_trading:
            self._portfolio_cache = self._build_portfolio_from_positions()
            logger.debug("纸面模式：更新组合缓存")
            return self._portfolio_cache

        # 订单执行后强制同步一次，确保获取最新持仓
        return await self.get_current_portfolio(force_sync=True)

    async def get_position(self, symbol: str, side: OrderSide | None = None) -> Position | None:
        """
        获取指定交易对持仓。
        """
        if self.paper_trading:
            if side:
                pos = self._positions.get(symbol)
                if pos and pos.side == side:
                    return pos
                return None
            return self._positions.get(symbol)

        portfolio = await self.get_current_portfolio()
        return portfolio.get_position(symbol, side)

    async def get_all_positions(self) -> List[Position]:
        """
        获取所有持仓列表。
        """
        if self.paper_trading:
            return list(self._positions.values())

        portfolio = await self.get_current_portfolio()
        return portfolio.positions

    async def calculate_metrics(self) -> PerformanceMetrics:
        """
        计算绩效指标。当前实现返回基础指标，后续可结合历史数据增强。
        """
        portfolio = await self.get_current_portfolio()
        now = datetime.now(timezone.utc)
        total_return = portfolio.total_return

        metrics = PerformanceMetrics(
            start_date=now,
            end_date=now,
            total_return=total_return,
            annualized_return=total_return,
            daily_returns=[Decimal("0")],
            volatility=Decimal("0"),
            max_drawdown=Decimal("0"),
            sharpe_ratio=Decimal("0"),
            sortino_ratio=Decimal("0"),
            calmar_ratio=Decimal("0"),
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            win_rate=Decimal("0"),
            avg_win=Decimal("0"),
            avg_loss=Decimal("0"),
            profit_factor=Decimal("0"),
            max_consecutive_wins=0,
            max_consecutive_losses=0,
        )
        return metrics

    # ------------------------------------------------------------------ #
    # 纸面模式辅助方法
    # ------------------------------------------------------------------ #

    def set_paper_positions(self, positions: List[Position], *, cash: Decimal) -> None:
        """
        为纸面模式设置持仓和现金。
        """
        if not self.paper_trading:
            raise TradingSystemError("set_paper_positions only available in paper mode")

        now = datetime.now(timezone.utc)
        unrealized_pnl = sum(pos.unrealized_pnl for pos in positions)
        margin_balance = sum(pos.value for pos in positions) - unrealized_pnl  # 持仓价值 - 盈亏 = 保证金
        wallet_balance = cash + unrealized_pnl + margin_balance

        portfolio = Portfolio(
            timestamp=int(now.timestamp() * 1000),
            dt=now,
            wallet_balance=wallet_balance,
            available_balance=cash,
            margin_balance=margin_balance,
            positions=positions,
            unrealized_pnl=unrealized_pnl,
            daily_pnl=Decimal("0"),
            total_return=Decimal("0"),
        )
        self._portfolio_cache = portfolio
        self._positions = {pos.symbol: pos for pos in positions}

    def apply_fill(self, symbol: str, side: OrderSide, amount: Decimal, price: Decimal) -> None:
        """
        在纸面模式下根据成交结果更新持仓。
        """
        if not self.paper_trading:
            raise TradingSystemError("apply_fill only available in paper mode")

        position = self._positions.get(symbol)
        value_change = amount * price

        if position:
            if side == OrderSide.BUY:
                new_amount = position.amount + amount
            else:
                new_amount = position.amount - amount
            new_value = new_amount * price
            position.amount = new_amount
            position.current_price = price
            position.value = new_value
            self._positions[symbol] = position
        else:
            if side == OrderSide.SELL:
                # 如果原本没有仓位，开空仓位
                order_side = OrderSide.SELL
            else:
                order_side = OrderSide.BUY
            position = Position(
                symbol=symbol,
                side=order_side,
                amount=amount,
                entry_price=price,
                current_price=price,
                unrealized_pnl=Decimal("0"),
                unrealized_pnl_percentage=Decimal("0"),
                value=value_change,
                stop_loss=None,
                take_profit=None,
            )
            self._positions[symbol] = position

        if self._portfolio_cache:
            cash = self._portfolio_cache.cash
            if side == OrderSide.BUY:
                cash -= value_change
            else:
                cash += value_change
            self._portfolio_cache.cash = cash
            self._portfolio_cache.positions = list(self._positions.values())
            self._portfolio_cache.total_value = cash + sum(
                pos.value for pos in self._positions.values()
            )

    # ------------------------------------------------------------------ #
    # 内部实现
    # ------------------------------------------------------------------ #

    async def _fetch_portfolio_from_database(self) -> Optional[Portfolio]:
        """
        从数据库读取最新的账户快照（由 AccountSyncService 同步）

        Returns:
            Portfolio 对象，如果数据库无数据则返回 None
        """
        if not self.db_manager:
            return None

        try:
            from src.services.database import TradingDAO

            async with self.db_manager.get_session() as session:
                dao = TradingDAO(session)

                # 获取最新的投资组合快照
                snapshots = await dao.get_portfolio_snapshots(
                    limit=1,
                    exchange_name=self.exchange_id,
                )
                if not snapshots:
                    return None

                snapshot_db = snapshots[0]

                # 获取当前持仓
                db_positions = await dao.get_open_positions(
                    exchange_name=self.exchange_id,
                )

                # 转换为 Position 对象
                positions = []
                from datetime import timezone

                for pos in db_positions:
                    opened_at_ms = None
                    if pos.opened_at:
                        try:
                            opened_dt = pos.opened_at
                            if opened_dt.tzinfo is None:
                                opened_dt = opened_dt.replace(tzinfo=timezone.utc)
                            opened_at_ms = int(opened_dt.timestamp() * 1000)
                        except Exception:  # pylint: disable=broad-except
                            opened_at_ms = None

                    positions.append(Position(
                        symbol=pos.symbol,
                        side=OrderSide.BUY if pos.side == 'buy' else OrderSide.SELL,
                        amount=Decimal(str(pos.amount)),
                        entry_price=Decimal(str(pos.entry_price)),
                        current_price=Decimal(str(pos.current_price)),
                        unrealized_pnl=Decimal(str(pos.unrealized_pnl or 0)),
                        unrealized_pnl_percentage=Decimal(str(pos.unrealized_pnl_percentage or 0)),
                        value=Decimal(str(pos.value)),
                        leverage=pos.leverage,
                        liquidation_price=Decimal(str(pos.liquidation_price)) if pos.liquidation_price else None,
                        stop_loss=Decimal(str(pos.stop_loss)) if pos.stop_loss else None,
                        take_profit=Decimal(str(pos.take_profit)) if pos.take_profit else None,
                        opened_at=opened_at_ms,
                    ))

                # 计算汇总数据
                total_unrealized_pnl = sum(p.unrealized_pnl for p in positions)
                wallet_balance = Decimal(str(snapshot_db.wallet_balance or 0))
                available_balance = Decimal(str(snapshot_db.available_balance or 0))

                # 创建 Portfolio 对象
                now = datetime.now(timezone.utc)
                portfolio = Portfolio(
                    timestamp=int(snapshot_db.datetime.timestamp() * 1000),
                    dt=now,
                    wallet_balance=wallet_balance,
                    available_balance=available_balance,
                    margin_balance=Decimal(str(snapshot_db.margin_balance or 0)),
                    positions=positions,
                    unrealized_pnl=total_unrealized_pnl,
                    daily_pnl=Decimal("0"),
                    total_return=Decimal("0"),
                )

                return portfolio

        except Exception as e:
            logger.error(f"从数据库读取账户数据失败: {e}", exc_info=True)
            return None

    def _convert_snapshot_to_portfolio(self, snapshot) -> Portfolio:
        """
        将 AccountSnapshot 转换为 Portfolio 对象

        Args:
            snapshot: AccountSnapshot 对象

        Returns:
            Portfolio 对象
        """
        # 计算总未实现盈亏
        unrealized_pnl = sum(p.unrealized_pnl for p in snapshot.positions)

        # 钱包余额 = 总余额 + 未实现盈亏（对于合约账户）
        wallet_balance = snapshot.total_balance + unrealized_pnl

        now = datetime.now(timezone.utc)
        return Portfolio(
            timestamp=int(snapshot.timestamp.timestamp() * 1000),
            dt=now,
            wallet_balance=wallet_balance,
            available_balance=snapshot.available_balance,
            margin_balance=snapshot.used_margin,
            positions=snapshot.positions,
            unrealized_pnl=unrealized_pnl,
            daily_pnl=Decimal("0"),
            total_return=Decimal("0"),
        )

    async def _fetch_portfolio_from_exchange_fallback(self) -> Portfolio:
        """
        回退方法：直接从交易所获取组合（当 AccountSyncService 不可用时）
        """
        # 使用统一的 ExchangeService 代替直接调用 exchange
        exchange_service = get_exchange_service()
        try:
            # 1. 获取账户余额
            balance = await exchange_service.fetch_balance()

            # 获取币安的余额字段
            available_balance = Decimal(str(balance.get("free", {}).get(self.base_currency, 0)))  # 可用保证金
            margin_balance = Decimal(str(balance.get("used", {}).get(self.base_currency, 0)))     # 已用保证金
            total_balance = Decimal(str(balance.get("total", {}).get(self.base_currency, 0)))     # 总余额

            # 2. 获取持仓列表
            positions_raw = []
            try:
                positions_raw = await exchange_service.fetch_positions()
            except Exception as exc:  # pylint: disable=broad-except
                logger.warning("获取持仓失败: %s", exc)

            # 3. 获取保护单(止盈/止损)并构建映射
            protection_orders: List[Dict[str, Any]] = []
            symbols_for_orders: Set[str] = {
                item.get("symbol") for item in positions_raw if item.get("symbol")
            }

            if symbols_for_orders:
                protection_orders = await self._fetch_protection_orders(exchange_service, symbols_for_orders)

            protection_map = self._build_protection_map(protection_orders)

            # 4. 解析持仓
            positions = self._parse_positions(positions_raw, protection_map)

            # 计算未实现盈亏
            unrealized_pnl = sum(pos.unrealized_pnl for pos in positions)

            # 钱包余额 = 总余额 + 未实现盈亏（对于合约账户）
            # 如果是现货账户，wallet_balance 就等于 total_balance
            wallet_balance = total_balance + unrealized_pnl

            logger.info(
                "账户同步完成 | 余额: %.2f %s | 持仓: %d | 未实现盈亏: %.2f %s",
                wallet_balance,
                self.base_currency,
                len(positions),
                unrealized_pnl,
                self.base_currency
            )

            now = datetime.now(timezone.utc)
            portfolio = Portfolio(
                timestamp=int(now.timestamp() * 1000),
                dt=now,
                wallet_balance=wallet_balance,
                available_balance=available_balance,
                margin_balance=margin_balance,
                positions=positions,
                unrealized_pnl=unrealized_pnl,
                daily_pnl=Decimal("0"),
                total_return=Decimal("0"),
            )
            return portfolio
        except Exception as exc:  # pylint: disable=broad-except
            raise PortfolioSyncError(
                message="Failed to synchronize portfolio",
                details={"exchange_id": self.exchange_id},
                original_exception=exc,
            ) from exc

    async def _fetch_protection_orders(
        self,
        exchange_service,  # ExchangeService instance
        symbols: Set[str],
    ) -> List[Dict[str, Any]]:
        """按交易对逐个获取未完成订单，避免 exchange 的全量查询限制。"""
        orders: List[Dict[str, Any]] = []

        for symbol in symbols:
            try:
                symbol_orders = await exchange_service.fetch_open_orders(symbol)
                orders.extend(symbol_orders)
            except Exception as exc:  # pylint: disable=broad-except
                logger.warning("获取 %s 未完成订单失败: %s", symbol, exc)

        return orders

    def _build_protection_map(
        self,
        open_orders: List[Dict[str, Any]],
    ) -> Dict[Tuple[str, OrderSide], Dict[str, Decimal]]:
        """根据未完成订单构建止盈/止损映射。"""
        protection_map: Dict[Tuple[str, OrderSide], Dict[str, Decimal]] = {}

        for idx, order in enumerate(open_orders):
            try:
                order_type = (order.get("type") or "").lower()
                if order_type not in {
                    "stop",
                    "stop_loss",
                    "stop_market",
                    "take_profit",
                    "take_profit_market",
                    "take_profit_limit",
                }:
                    continue

                symbol = order.get("symbol")
                side_raw = (order.get("side") or "").lower()
                if not symbol or side_raw not in {"buy", "sell"}:
                    continue

                info = order.get("info", {}) or {}
                reduce_only = bool(order.get("reduceOnly"))
                close_position_flag = str(info.get("closePosition", "")).lower() == "true"
                if not (reduce_only or close_position_flag):
                    # 过滤掉开仓单/普通委托
                    continue

                stop_price_raw = (
                    order.get("stopPrice")
                    or order.get("price")
                    or info.get("stopPrice")
                )
                if not stop_price_raw or str(stop_price_raw) in {"0", "0.0"}:
                    continue

                price = Decimal(str(stop_price_raw))

                # 平空仓(买入)对应 SHORT 仓位，平多仓(卖出)对应 LONG 仓位
                target_side = OrderSide.SELL if side_raw == "buy" else OrderSide.BUY
                key = (symbol, target_side)
                protection = protection_map.setdefault(key, {})

                if order_type in {"stop", "stop_loss", "stop_market"}:
                    protection["stop_loss"] = price
                else:
                    protection["take_profit"] = price

            except Exception as exc:  # pylint: disable=broad-except
                logger.debug("解析保护单失败 [%d]: %s", idx, exc)

        return protection_map

    def _parse_positions(
        self,
        raw_positions: List[Dict[str, Any]],
        protection_map: Optional[Dict[Tuple[str, OrderSide], Dict[str, Decimal]]] = None,
    ) -> List[Position]:
        positions: List[Position] = []
        protection_map = protection_map or {}
        for idx, item in enumerate(raw_positions):
            try:
                symbol = item.get("symbol")
                if not symbol:
                    continue

                amount = Decimal(str(item.get("contracts") or item.get("amount") or 0))
                if amount == 0:
                    continue

                # Binance USDM 双向持仓模式下，需要检查 side 字段
                # side 字段: "long" 或 "short"
                position_side = item.get("side", "").lower()
                if position_side == "short":
                    side = OrderSide.SELL
                elif position_side == "long":
                    side = OrderSide.BUY
                else:
                    # 兼容旧逻辑（单向持仓模式）
                    side = OrderSide.BUY if amount >= 0 else OrderSide.SELL

                entry_price = Decimal(str(item.get("entryPrice") or item.get("avgPrice") or 0))
                current_price = Decimal(str(item.get("markPrice") or item.get("last") or entry_price))
                value = abs(amount) * current_price
                unrealized = Decimal(str(item.get("unrealizedPnl", 0)))

                # 获取强平价格 (Binance: liquidationPrice)
                # CCXT 规范化后可能在顶层,也可能在 info 字段中
                liquidation_price_raw = item.get("liquidationPrice") or item.get("info", {}).get("liquidationPrice")
                liquidation_price = None
                if liquidation_price_raw and liquidation_price_raw not in (0, "0"):
                    try:
                        liquidation_price = Decimal(str(liquidation_price_raw))
                    except (ValueError, TypeError):
                        logger.warning("%s 强平价格解析失败: %s", symbol, liquidation_price_raw)
                        liquidation_price = None

                # 获取杠杆倍数
                # Binance fetch_positions 不返回 leverage 字段，需要计算
                leverage_raw = item.get("leverage") or item.get("info", {}).get("leverage")
                leverage = None

                if leverage_raw:
                    try:
                        leverage = int(leverage_raw)
                    except (ValueError, TypeError):
                        logger.warning("%s 杠杆倍数解析失败: %s", symbol, leverage_raw)
                else:
                    # 通过持仓价值和保证金计算杠杆
                    try:
                        notional = abs(float(item.get("notional", 0)))
                        initial_margin = float(item.get("initialMargin", 0))

                        if initial_margin > 0 and notional > 0:
                            calculated_leverage = round(notional / initial_margin)
                            leverage = int(calculated_leverage)
                    except (ValueError, TypeError, KeyError):
                        pass

                # 获取开仓时间 (Binance: updateTime)
                # CCXT可能在顶层或info字段中
                opened_at_raw = item.get("timestamp") or item.get("info", {}).get("updateTime")
                opened_at = None
                if opened_at_raw:
                    try:
                        # Binance返回的是毫秒时间戳
                        opened_at = int(opened_at_raw)
                    except (ValueError, TypeError):
                        pass

                protection = protection_map.get((symbol, side), {})

                position = Position(
                    symbol=symbol,
                    side=side,
                    amount=abs(amount),
                    entry_price=entry_price,
                    current_price=current_price,
                    unrealized_pnl=unrealized,
                    unrealized_pnl_percentage=Decimal("0"),
                    value=value,
                    stop_loss=protection.get("stop_loss"),
                    take_profit=protection.get("take_profit"),
                    liquidation_price=liquidation_price,
                    leverage=leverage,
                    opened_at=opened_at,
                )
                positions.append(position)
            except Exception as exc:  # pylint: disable=broad-except
                logger.warning("解析持仓失败: %s", exc)
        return positions

    def _build_portfolio_from_positions(self) -> Portfolio:
        now = datetime.now(timezone.utc)
        positions = list(self._positions.values())
        cash = Decimal("0")
        if self._portfolio_cache:
            cash = self._portfolio_cache.cash

        total_value = cash + sum(pos.value for pos in positions)
        return Portfolio(
            timestamp=int(now.timestamp() * 1000),
            dt=now,
            total_value=total_value,
            cash=cash,
            positions=positions,
            total_pnl=Decimal("0"),
            daily_pnl=Decimal("0"),
            total_return=Decimal("0"),
        )

    async def close(self) -> None:
        """关闭与交易所的连接"""
        # Note: ExchangeService 是全局单例，不需要在这里关闭
        # 如果需要关闭，应该在应用退出时统一关闭 ExchangeService
        logger.debug("PortfolioManager closed (ExchangeService is managed globally)")
