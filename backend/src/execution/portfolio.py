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
    ) -> None:
        self.exchange_id = exchange_id
        self.config = config or {}
        self.paper_trading = paper_trading
        self.base_currency = base_currency
        self.sync_interval_seconds = sync_interval_seconds
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
          1. 如果 force_sync=True，强制从交易所同步
          2. 如果距离上次同步超过 sync_interval_seconds，自动同步
          3. 否则使用缓存（避免频繁API调用）
          4. 并发请求时使用锁，确保同一时刻只有一个实际的API调用

        Args:
            force_sync: 是否强制从交易所同步（订单执行后应设为True）
        """
        if self.paper_trading:
            if not self._portfolio_cache:
                self._portfolio_cache = self._build_portfolio_from_positions()
            logger.debug("纸面模式：使用缓存组合 (总值: %s USDT)", self._portfolio_cache.total_value)
            return self._portfolio_cache

        # 检查是否需要同步
        import time
        now = time.time()
        time_since_last_sync = now - self._last_sync_time
        need_sync = force_sync or time_since_last_sync >= self.sync_interval_seconds

        if not need_sync and self._portfolio_cache:
            logger.debug(
                "使用缓存组合 (上次同步: %.0f秒前, 间隔: %d秒)",
                time_since_last_sync,
                self.sync_interval_seconds,
            )
            return self._portfolio_cache

        # 使用锁确保并发请求时只执行一次同步
        async with self._sync_lock:
            # 双重检查：可能在等待锁的过程中，另一个协程已经完成了同步
            now = time.time()
            time_since_last_sync = now - self._last_sync_time

            # 去重逻辑：即使是force_sync，如果在去重窗口内已同步过，也使用缓存
            # 这样可以避免并发执行多个信号时的重复API调用
            if (
                self._portfolio_cache
                and time_since_last_sync < self._sync_debounce_seconds
            ):
                logger.debug(
                    "去重窗口内已同步(%.1f秒前)，使用缓存 (去重窗口: %.1f秒)",
                    time_since_last_sync,
                    self._sync_debounce_seconds,
                )
                return self._portfolio_cache

            # 正常的同步检查
            need_sync = force_sync or time_since_last_sync >= self.sync_interval_seconds
            if not need_sync and self._portfolio_cache:
                logger.debug(
                    "其他协程已完成同步，使用缓存组合 (上次同步: %.0f秒前)",
                    time_since_last_sync,
                )
                return self._portfolio_cache

            # 执行同步
            sync_reason = "强制同步" if force_sync else f"定期同步 (已过 {time_since_last_sync:.0f}秒)"
            logger.info("从交易所同步持仓和余额... (%s)", sync_reason)
            portfolio = await self._fetch_portfolio_from_exchange()
            self._portfolio_cache = portfolio
            self._last_sync_time = now
            logger.info(
                "✓ 同步完成 | 余额: %s USDT | 持仓数: %d | 总值: %s USDT",
                portfolio.cash,
                len(portfolio.positions),
                portfolio.total_value,
            )
            return portfolio

    async def update_portfolio(self) -> Portfolio:
        """
        强制同步最新组合（通常在订单执行后调用）。
        等同于 get_current_portfolio(force_sync=True)
        """
        if self.paper_trading:
            self._portfolio_cache = self._build_portfolio_from_positions()
            logger.debug("纸面模式：更新组合缓存")
            return self._portfolio_cache

        # 强制从交易所同步
        return await self.get_current_portfolio(force_sync=True)

    async def get_position(self, symbol: str) -> Position | None:
        """
        获取指定交易对持仓。
        """
        if self.paper_trading:
            return self._positions.get(symbol)

        portfolio = await self.get_current_portfolio()
        return portfolio.get_position(symbol)

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

    async def _fetch_portfolio_from_exchange(self) -> Portfolio:
        # 使用统一的 ExchangeService 代替直接调用 exchange
        exchange_service = get_exchange_service()
        try:
            # 1. 获取账户余额
            logger.debug("正在调用 fetch_balance()...")
            balance = await exchange_service.fetch_balance()

            # 获取币安的余额字段
            available_balance = Decimal(str(balance.get("free", {}).get(self.base_currency, 0)))  # 可用保证金
            margin_balance = Decimal(str(balance.get("used", {}).get(self.base_currency, 0)))     # 已用保证金
            total_balance = Decimal(str(balance.get("total", {}).get(self.base_currency, 0)))     # 总余额

            logger.info("  ├─ 可用保证金 (Available): %s %s", available_balance, self.base_currency)
            logger.info("  ├─ 已用保证金 (Used): %s %s", margin_balance, self.base_currency)
            logger.info("  ├─ 总余额 (Total): %s %s", total_balance, self.base_currency)

            # 2. 获取持仓列表
            positions_raw = []
            try:
                logger.debug("正在调用 fetch_positions()...")
                positions_raw = await exchange_service.fetch_positions()
                logger.info("  ├─ 原始持仓数据: %d 条", len(positions_raw))
            except Exception as exc:  # pylint: disable=broad-except
                logger.warning("  └─ 获取持仓失败: %s", exc)

            # 3. 获取保护单(止盈/止损)并构建映射
            protection_orders: List[Dict[str, Any]] = []
            symbols_for_orders: Set[str] = {
                item.get("symbol") for item in positions_raw if item.get("symbol")
            }

            if symbols_for_orders:
                protection_orders = await self._fetch_protection_orders(exchange_service, symbols_for_orders)
            else:
                logger.debug("  └─ 当前无持仓，跳过保护单查询")

            protection_map = self._build_protection_map(protection_orders)

            # 4. 解析持仓
            positions = self._parse_positions(positions_raw, protection_map)
            if positions:
                logger.info("  ├─ 解析后持仓:")
                for pos in positions:
                    logger.info(
                        "  │   %s: %.4f @ %.4f (价值: %.2f USDT, PnL: %.2f)",
                        pos.symbol,
                        pos.amount,
                        pos.current_price,
                        pos.value,
                        pos.unrealized_pnl,
                    )
            else:
                logger.info("  └─ 当前无持仓")

            # 计算未实现盈亏
            unrealized_pnl = sum(pos.unrealized_pnl for pos in positions)

            # 钱包余额 = 总余额 + 未实现盈亏（对于合约账户）
            # 如果是现货账户，wallet_balance 就等于 total_balance
            wallet_balance = total_balance + unrealized_pnl

            logger.info("  ├─ 未实现盈亏 (Unrealized PNL): %s %s", unrealized_pnl, self.base_currency)
            logger.info("  └─ 钱包余额 (Wallet Balance): %s %s", wallet_balance, self.base_currency)

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
                logger.debug("  ├─ 调用 fetch_open_orders(%s)...", symbol)
                symbol_orders = await exchange_service.fetch_open_orders(symbol)
                logger.info("  │   %s 未完成订单: %d 条", symbol, len(symbol_orders))
                orders.extend(symbol_orders)
            except Exception as exc:  # pylint: disable=broad-except
                logger.warning("  └─ 获取 %s 未完成订单失败: %s", symbol, exc)

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
                # 打印原始持仓数据用于调试
                logger.debug("持仓原始数据 [%d]: %s", idx, item)

                symbol = item.get("symbol")
                if not symbol:
                    logger.debug("跳过无效持仓数据 [%d]: 缺少 symbol", idx)
                    continue

                amount = Decimal(str(item.get("contracts") or item.get("amount") or 0))
                if amount == 0:
                    logger.debug("跳过零持仓: %s", symbol)
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
                    logger.debug("未找到 side 字段，使用 amount 符号判断方向: %s", side.value)

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
                        logger.debug("%s 强平价格: %s", symbol, liquidation_price)
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
                        logger.debug("%s 杠杆倍数(直接获取): %d", symbol, leverage)
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
                            logger.debug("%s 杠杆倍数(计算): %dx (名义价值=%.2f, 保证金=%.2f)",
                                       symbol, leverage, notional, initial_margin)
                        else:
                            logger.debug("%s 无法计算杠杆: notional=%s, initialMargin=%s",
                                       symbol, notional, initial_margin)
                    except (ValueError, TypeError, KeyError) as e:
                        logger.debug("%s 杠杆计算失败: %s", symbol, e)

                # 获取开仓时间 (Binance: updateTime)
                # CCXT可能在顶层或info字段中
                opened_at_raw = item.get("timestamp") or item.get("info", {}).get("updateTime")
                opened_at = None
                if opened_at_raw:
                    try:
                        # Binance返回的是毫秒时间戳
                        opened_at = int(opened_at_raw)
                        logger.debug("%s 开仓时间: %s", symbol, opened_at)
                    except (ValueError, TypeError):
                        logger.debug("%s 开仓时间解析失败: %s", symbol, opened_at_raw)

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
                logger.debug("解析持仓 [%d]: %s %s %.4f", idx, symbol, side.value, abs(amount))
            except Exception as exc:  # pylint: disable=broad-except
                logger.warning("解析持仓失败 [%d]: %s | 错误: %s", idx, item, exc)
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
