"""
订单执行模块

提供基于 CCXT 的订单执行器，同时支持纸面交易模式以便于测试和模拟。
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

import ccxt.async_support as ccxt  # type: ignore

from src.core.exceptions import (
    OrderCancellationError,
    OrderExecutionError,
    OrderQueryError,
    TradingSystemError,
)
from src.core.logger import get_logger
from src.models.trade import Order, OrderSide, OrderStatus, OrderType


logger = get_logger(__name__)

BINANCE_USDM_TESTNET_API: Dict[str, str] = {
    "dapiPublic": "https://demo-fapi.binance.com/dapi/v1",
    "dapiPrivate": "https://demo-fapi.binance.com/dapi/v1",
    "dapiPrivateV2": "https://demo-fapi.binance.com/dapi/v2",
    "fapiPublic": "https://demo-fapi.binance.com/fapi/v1",
    "fapiPublicV2": "https://demo-fapi.binance.com/fapi/v2",
    "fapiPublicV3": "https://demo-fapi.binance.com/fapi/v3",
    "fapiPrivate": "https://demo-fapi.binance.com/fapi/v1",
    "fapiPrivateV2": "https://demo-fapi.binance.com/fapi/v2",
    "fapiPrivateV3": "https://demo-fapi.binance.com/fapi/v3",
    "public": "https://testnet.binance.vision/api/v3",
    "private": "https://testnet.binance.vision/api/v3",
    "v1": "https://testnet.binance.vision/api/v1",
}


class CCXTOrderExecutor:
    """
    基于 CCXT 的订单执行器。

    Attributes:
        exchange_id: 交易所 ID，例如 "binance"
        config: CCXT 初始化配置
        paper_trading: 是否启用纸面交易（不触发真实下单）
    """

    SIMULATED_LATENCY_MS = 50

    def __init__(
        self,
        exchange_id: str = "binance",
        config: Optional[Dict[str, Any]] = None,
        *,
        paper_trading: bool = False,
    ) -> None:
        self.exchange_id = exchange_id
        self.config = config or {}
        self.paper_trading = paper_trading
        self._exchange: Optional[ccxt.Exchange] = None
        self._lock = asyncio.Lock()
        self._orders: Dict[str, Order] = {}
        self._leverage_cache: Dict[str, int] = {}

    # ------------------------------------------------------------------ #
    # public API
    # ------------------------------------------------------------------ #

    async def create_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        amount: Decimal,
        price: Decimal | None = None,
        **kwargs: Any,
    ) -> Order:
        """
        创建订单。如果处于纸面交易模式，则直接生成模拟订单。
        """
        if self.paper_trading:
            order = await self._simulate_order(
                symbol=symbol,
                side=side,
                order_type=order_type,
                amount=amount,
                price=price,
                **kwargs,
            )
            logger.info("纸面订单已创建：%s id=%s", symbol, order.id)
            return order

        exchange = await self._get_exchange()
        params = dict(kwargs) if kwargs else {}
        ccxt_order_type = self._map_order_type(order_type, price=price, params=params)

        # Binance 永续合约需要指定持仓方向
        if self.exchange_id in ["binanceusdm", "binance", "binancecoinm"]:
            # 检查是否为平仓订单（用于确定 positionSide）
            is_reduce_only = params.get("reduceOnly", False)

            # 如果调用方没有指定 positionSide，则根据订单方向自动判断
            if "positionSide" not in params:
                # 双向持仓模式 (Hedge Mode):
                # - 做多订单: positionSide = "LONG"
                # - 做空订单: positionSide = "SHORT"
                # - 平仓订单: 使用与持仓相同的 positionSide (通过 reduceOnly 区分)
                #
                # 判断逻辑:
                # 1. 如果有 reduceOnly=True，说明是平仓订单
                #    - BUY + reduceOnly = 平空仓 -> SHORT
                #    - SELL + reduceOnly = 平多仓 -> LONG
                # 2. 否则是开仓订单
                #    - BUY = 开多 -> LONG
                #    - SELL = 开空 -> SHORT

                if is_reduce_only:
                    # 平仓订单: 方向与买卖相反
                    # BUY (平空) -> SHORT, SELL (平多) -> LONG
                    params["positionSide"] = "SHORT" if side == OrderSide.BUY else "LONG"
                else:
                    # 开仓订单: 方向与买卖一致
                    # BUY (开多) -> LONG, SELL (开空) -> SHORT
                    params["positionSide"] = "LONG" if side == OrderSide.BUY else "SHORT"

                logger.debug(
                    "Binance订单自动设置 positionSide=%s (双向持仓模式): symbol=%s, side=%s, type=%s, reduceOnly=%s",
                    params["positionSide"], symbol, side.value, ccxt_order_type, is_reduce_only
                )
            else:
                logger.debug(
                    "Binance订单使用调用方指定的 positionSide=%s: symbol=%s, side=%s, type=%s",
                    params["positionSide"], symbol, side.value, ccxt_order_type
                )

            # 对于止损止盈订单，Binance USDM 合约需要特殊参数
            # 使用 closePosition=true 来自动平仓，而不是 reduceOnly
            if ccxt_order_type in ["stop_market", "take_profit_market", "stop", "take_profit"]:
                if "reduceOnly" in params:
                    params.pop("reduceOnly")
                # 设置 closePosition=true 表示完全平掉该方向的仓位
                params["closePosition"] = True
                # workingType 指定触发价格类型
                params["workingType"] = "CONTRACT_PRICE"  # 使用最新成交价触发
                logger.debug(
                    "Binance USDM止损止盈订单参数: symbol=%s, type=%s, closePosition=True, workingType=CONTRACT_PRICE",
                    symbol, ccxt_order_type
                )

            # 对于市价平仓单，币安不需要 reduceOnly 参数（positionSide 已经足够）
            # 移除 reduceOnly 避免报错: "Parameter 'reduceonly' sent when not required."
            elif ccxt_order_type.upper() == "MARKET" and is_reduce_only:
                if "reduceOnly" in params:
                    params.pop("reduceOnly")
                logger.debug(
                    "Binance市价平仓单: 移除 reduceOnly 参数，仅使用 positionSide=%s",
                    params.get("positionSide")
                )

        try:
            response = await exchange.create_order(
                symbol=symbol,
                type=ccxt_order_type,
                side=side.value,
                amount=float(amount),
                price=float(price) if price is not None else None,
                params=params,
            )
            order = self._convert_order(response)
            self._orders[order.id] = order
            return order
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Failed to create order on %s: %s", self.exchange_id, exc)
            raise OrderExecutionError(
                message="Failed to create order",
                details={"symbol": symbol, "side": side.value, "type": order_type.value},
                original_exception=exc,
            ) from exc

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """
        取消订单。纸面模式下直接修改订单状态。
        """
        if self.paper_trading:
            order = self._orders.get(order_id)
            if not order:
                raise OrderQueryError(
                    message="Order not found in paper trading store",
                    details={"order_id": order_id, "symbol": symbol},
                )
            if order.status in {OrderStatus.FILLED, OrderStatus.CANCELED}:
                return False
            order.status = OrderStatus.CANCELED
            self._orders[order_id] = order
            return True

        exchange = await self._get_exchange()
        try:
            await exchange.cancel_order(order_id, symbol)
            # 更新本地缓存
            cached = self._orders.get(order_id)
            if cached:
                cached.status = OrderStatus.CANCELED
                self._orders[order_id] = cached
            return True
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Failed to cancel order %s: %s", order_id, exc)
            raise OrderCancellationError(
                message="Failed to cancel order",
                details={"order_id": order_id, "symbol": symbol},
                original_exception=exc,
            ) from exc

    async def get_order(self, order_id: str, symbol: str) -> Order:
        """
        查询订单状态。优先从本地缓存读取，若没有则向交易所查询。
        """
        if order_id in self._orders:
            return self._orders[order_id]

        if self.paper_trading:
            raise OrderQueryError(
                message="Order not found in paper trading store",
                details={"order_id": order_id},
            )

        exchange = await self._get_exchange()
        try:
            response = await exchange.fetch_order(order_id, symbol)
            order = self._convert_order(response)
            self._orders[order_id] = order
            return order
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Failed to fetch order %s: %s", order_id, exc)
            raise OrderQueryError(
                message="Failed to fetch order",
                details={"order_id": order_id, "symbol": symbol},
                original_exception=exc,
            ) from exc

    async def get_open_orders(self, symbol: str | None = None) -> List[Order]:
        """
        获取所有未完成订单。
        """
        open_status = {
            OrderStatus.OPEN,
            OrderStatus.PENDING,
            OrderStatus.PARTIALLY_FILLED,
        }

        if self.paper_trading:
            return [
                order
                for order in self._orders.values()
                if order.status in open_status
                and (symbol is None or order.symbol == symbol)
            ]

        exchange = await self._get_exchange()
        try:
            response = await exchange.fetch_open_orders(symbol)
            orders = [self._convert_order(item) for item in response]
            for order in orders:
                self._orders[order.id] = order
            return orders
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Failed to fetch open orders: %s", exc)
            raise OrderQueryError(
                message="Failed to fetch open orders",
                details={"symbol": symbol},
                original_exception=exc,
            ) from exc

    async def set_leverage(
        self,
        symbol: str,
        leverage: int,
    ) -> bool:
        """
        设置交易对的杠杆倍数（仅合约交易需要）

        Args:
            symbol: 交易对
            leverage: 杠杆倍数 (1-125)

        Returns:
            True if successful, False otherwise
        """
        if self.paper_trading:
            logger.info("纸面交易模式，跳过杠杆设置")
            self._leverage_cache[symbol] = leverage
            return True

        cached = self._leverage_cache.get(symbol)
        if cached == leverage:
            logger.debug("%s 杠杆已是 %dx，跳过重复设置", symbol, leverage)
            return True

        try:
            exchange = await self._get_exchange()

            # 检查交易所是否支持设置杠杆
            if not hasattr(exchange, 'set_leverage'):
                logger.warning(f"{self.exchange_id} 不支持设置杠杆")
                return False

            # 设置杠杆
            await exchange.set_leverage(leverage, symbol)
            logger.info(f"✓ {symbol} 杠杆已设置为 {leverage}x")
            self._leverage_cache[symbol] = leverage
            return True

        except Exception as exc:
            logger.error(f"设置杠杆失败 {symbol} {leverage}x: {exc}", exc_info=True)
            if symbol in self._leverage_cache:
                self._leverage_cache.pop(symbol, None)
            return False

    async def create_order_with_stops(
        self,
        symbol: str,
        side: OrderSide,
        amount: Decimal,
        price: Optional[Decimal] = None,
        stop_loss: Optional[Decimal] = None,
        take_profit: Optional[Decimal] = None,
        leverage: Optional[int] = None,
        **kwargs: Any,
    ) -> Dict[str, Order]:
        """
        创建订单并同时设置止盈止损。

        这是解决时效性问题的关键方法：
        - 主订单立即执行
        - 止损止盈订单挂在交易所服务器，触发即执行（0延迟）
        - 即使程序挂掉，止损也会生效（24/7保护）

        Args:
            symbol: 交易对
            side: 买卖方向
            amount: 数量
            price: 限价单价格（None为市价单）
            stop_loss: 止损价格
            take_profit: 止盈价格

        Returns:
            {
                "main": 主订单,
                "stop_loss": 止损订单 (如果设置),
                "take_profit": 止盈订单 (如果设置)
            }
        """
        result: Dict[str, Order] = {}

        # 0. 设置杠杆（如果指定）
        if leverage is not None and leverage > 1:
            await self.set_leverage(symbol, leverage)

        # 1. 创建主订单（开仓）
        order_type = OrderType.LIMIT if price else OrderType.MARKET
        main_order = await self.create_order(
            symbol=symbol,
            side=side,
            order_type=order_type,
            amount=amount,
            price=price,
            **kwargs,
        )
        result["main"] = main_order
        logger.info(
            "✓ 主订单已创建：%s %s %s @ %s",
            symbol, side.value, amount, price or "市价"
        )

        # 等待主订单成交（市价单通常立即成交）
        if order_type == OrderType.MARKET:
            await asyncio.sleep(0.5)  # 给交易所一点时间处理

        # 2. 创建止损订单（如果设置）
        if stop_loss:
            try:
                # 止损订单方向与主订单相反（平仓）
                stop_side = OrderSide.SELL if side == OrderSide.BUY else OrderSide.BUY
                logger.debug(
                    "准备创建止损订单: symbol=%s, side=%s, stopPrice=%s",
                    symbol, stop_side.value, stop_loss
                )
                # 合并参数，确保 reduceOnly 生效
                # 双向持仓模式下，平仓订单需要指定正确的 positionSide:
                # - 平多仓 (SELL): positionSide = "LONG"
                # - 平空仓 (BUY): positionSide = "SHORT"
                stop_params = {
                    **kwargs,
                    "stopPrice": float(stop_loss),
                    "reduceOnly": True,
                    # positionSide 会由 create_order 自动根据 side + reduceOnly 判断
                }
                stop_order = await self.create_order(
                    symbol=symbol,
                    side=stop_side,
                    order_type=OrderType.STOP_LOSS,
                    amount=amount,
                    price=None,  # 止损市价单
                    **stop_params,
                )
                result["stop_loss"] = stop_order
                logger.info(
                    "✓ 止损订单已设置：%s @ %s (保护下行 %.2f%%), 订单ID: %s",
                    symbol, stop_loss,
                    abs((stop_loss - (price or stop_loss)) / (price or stop_loss) * 100) if price else 0,
                    stop_order.id
                )
            except Exception as exc:  # pylint: disable=broad-except
                logger.error("❌ 止损订单创建失败: %s", exc, exc_info=True)
                # 不抛出异常，主订单已经成功

        # 3. 创建止盈订单（如果设置）
        if take_profit:
            try:
                # 止盈订单方向与主订单相反（平仓）
                tp_side = OrderSide.SELL if side == OrderSide.BUY else OrderSide.BUY
                logger.debug(
                    "准备创建止盈订单: symbol=%s, side=%s, stopPrice=%s",
                    symbol, tp_side.value, take_profit
                )
                # 合并参数，确保 reduceOnly 生效
                # 双向持仓模式下，平仓订单需要指定正确的 positionSide:
                # - 平多仓 (SELL): positionSide = "LONG"
                # - 平空仓 (BUY): positionSide = "SHORT"
                tp_params = {
                    **kwargs,
                    "stopPrice": float(take_profit),
                    "reduceOnly": True,
                    # positionSide 会由 create_order 自动根据 side + reduceOnly 判断
                }
                tp_order = await self.create_order(
                    symbol=symbol,
                    side=tp_side,
                    order_type=OrderType.TAKE_PROFIT,
                    amount=amount,
                    price=None,  # 止盈市价单
                    **tp_params,
                )
                result["take_profit"] = tp_order
                logger.info(
                    "✓ 止盈订单已设置：%s @ %s (目标收益 %.2f%%), 订单ID: %s",
                    symbol, take_profit,
                    abs((take_profit - (price or take_profit)) / (price or take_profit) * 100) if price else 0,
                    tp_order.id
                )
            except Exception as exc:  # pylint: disable=broad-except
                logger.error("❌ 止盈订单创建失败: %s", exc, exc_info=True)
                # 不抛出异常，主订单已经成功

        logger.info(
            "🎯 订单组合已完成：主订单=%s, 止损=%s, 止盈=%s",
            "成功" if "main" in result else "失败",
            "已设置" if "stop_loss" in result else "未设置",
            "已设置" if "take_profit" in result else "未设置"
        )

        return result

    async def create_protective_orders(
        self,
        *,
        symbol: str,
        position_side: OrderSide,
        amount: Decimal,
        current_price: Decimal,
        stop_loss: Optional[Decimal] = None,
        take_profit: Optional[Decimal] = None,
    ) -> Dict[str, Order]:
        """
        为已有仓位设置单独的止损/止盈订单。
        """
        orders: Dict[str, Order] = {}
        if amount <= 0:
            return orders

        hedge_side = OrderSide.SELL if position_side == OrderSide.BUY else OrderSide.BUY

        async def _create(
            order_type: OrderType,
            trigger_price: Decimal,
            label: str,
        ) -> Optional[Order]:
            try:
                return await self.create_order(
                    symbol=symbol,
                    side=hedge_side,
                    order_type=order_type,
                    amount=amount,
                    price=None,
                    stopPrice=float(trigger_price),
                    reduceOnly=True,
                    # positionSide 会由 create_order 自动根据 side + reduceOnly 判断
                    # 双向持仓模式: SELL+reduceOnly=LONG, BUY+reduceOnly=SHORT
                )
            except Exception as exc:  # pylint: disable=broad-except
                logger.error("%s 保护单创建失败: %s", label, exc)
                return None

        if stop_loss:
            valid = (
                (position_side == OrderSide.BUY and stop_loss < current_price)
                or (position_side == OrderSide.SELL and stop_loss > current_price)
            )
            if valid:
                order = await _create(OrderType.STOP_LOSS, stop_loss, "止损")
                if order:
                    orders["stop_loss"] = order
            else:
                logger.warning(
                    "%s 止损价 %s 与当前价 %s 不符，跳过设置。",
                    symbol,
                    stop_loss,
                    current_price,
                )

        if take_profit:
            valid = (
                (position_side == OrderSide.BUY and take_profit > current_price)
                or (position_side == OrderSide.SELL and take_profit < current_price)
            )
            if valid:
                order = await _create(OrderType.TAKE_PROFIT, take_profit, "止盈")
                if order:
                    orders["take_profit"] = order
            else:
                logger.warning(
                    "%s 止盈价 %s 与当前价 %s 不符，跳过设置。",
                    symbol,
                    take_profit,
                    current_price,
                )

        return orders

    async def close(self) -> None:
        """关闭交易所连接"""
        if self._exchange:
            try:
                await self._exchange.close()
            except Exception as exc:  # pylint: disable=broad-except
                logger.warning("Failed to close exchange connection: %s", exc)
            finally:
                self._exchange = None

    # ------------------------------------------------------------------ #
    # 内部实现
    # ------------------------------------------------------------------ #

    async def _get_exchange(self) -> ccxt.Exchange:
        if self.paper_trading:
            raise TradingSystemError(
                message="Paper trading mode does not use a live exchange connection"
            )

        if self._exchange:
            return self._exchange

        async with self._lock:
            if self._exchange:
                return self._exchange
            try:
                exchange_class = getattr(ccxt, self.exchange_id)
                self._exchange = exchange_class(self.config)
                self._enable_sandbox_if_needed()
                await self._exchange.load_markets()
                logger.info("Initialized CCXT exchange: %s", self.exchange_id)
            except Exception as exc:  # pylint: disable=broad-except
                raise TradingSystemError(
                    message="Failed to initialize exchange",
                    details={"exchange_id": self.exchange_id},
                    original_exception=exc,
                ) from exc
        return self._exchange

    async def _simulate_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        amount: Decimal,
        price: Decimal | None,
        **kwargs: Any,
    ) -> Order:
        """
        创建模拟订单。默认假设立即完全成交。
        """
        await asyncio.sleep(self.SIMULATED_LATENCY_MS / 1000)
        order_id = kwargs.get("client_order_id") or str(uuid.uuid4())
        timestamp = int(datetime.now(timezone.utc).timestamp() * 1000)
        dt = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)

        fill_price = price or Decimal(str(kwargs.get("mark_price", "0")))

        # 止损止盈订单在纸面交易中保持OPEN状态（等待触发）
        is_stop_order = order_type in {OrderType.STOP_LOSS, OrderType.TAKE_PROFIT}
        is_filled = (order_type == OrderType.MARKET) and not is_stop_order

        # 提取止损止盈价格
        stop_price = kwargs.get("stopPrice")
        stop_price_decimal = Decimal(str(stop_price)) if stop_price else None

        order = Order(
            id=order_id,
            client_order_id=order_id,
            timestamp=timestamp,
            dt=dt,
            symbol=symbol,
            side=side,
            type=order_type,
            status=OrderStatus.FILLED if is_filled else OrderStatus.OPEN,
            price=price,
            amount=amount,
            filled=amount if is_filled else Decimal("0"),
            remaining=Decimal("0") if is_filled else amount,
            cost=(fill_price or Decimal("0")) * amount if is_filled else Decimal("0"),
            average=fill_price if is_filled else None,
            fee=None,
            stop_price=stop_price_decimal,
            exchange=self.exchange_id,
            info={"paper_trading": True, "params": kwargs},
        )
        self._orders[order.id] = order
        return order

    @staticmethod
    def _to_decimal(value: Any, *, default: Decimal | str | None = Decimal("0"), allow_none: bool = False) -> Decimal | None:
        """将任意数值安全转换为 Decimal。"""
        if value in (None, "", "None"):
            if allow_none:
                return None
            return Decimal(str(default)) if default is not None else None

        try:
            return Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            if allow_none:
                return None
            return Decimal(str(default)) if default is not None else None

    def _convert_order(self, data: Dict[str, Any]) -> Order:
        """
        将 CCXT 返回的订单结构转换为内部模型。
        """
        timestamp = data.get("timestamp") or data.get("datetime")
        if isinstance(timestamp, str):
            try:
                dt_obj = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                timestamp = int(dt_obj.timestamp() * 1000)
            except ValueError:
                timestamp = None

        dt = (
            datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)
            if timestamp is not None
            else datetime.now(timezone.utc)
        )

        status = data.get("status", "open") or "open"

        # 将 CCXT/Binance 的订单类型映射到内部枚举
        raw_type = (data.get("type") or "market").lower()
        type_mapping = {
            "market": OrderType.MARKET,
            "limit": OrderType.LIMIT,
            "stop": OrderType.STOP_LOSS,
            "stop_market": OrderType.STOP_LOSS,
            "stop_loss": OrderType.STOP_LOSS,
            "stop_loss_limit": OrderType.STOP_LOSS_LIMIT,
            "take_profit": OrderType.TAKE_PROFIT,
            "take_profit_market": OrderType.TAKE_PROFIT,
            "take_profit_limit": OrderType.TAKE_PROFIT_LIMIT,
        }
        order_type = type_mapping.get(raw_type, OrderType.MARKET)

        price = self._to_decimal(data.get("price"), allow_none=True)
        amount = self._to_decimal(data.get("amount", 0))
        filled = self._to_decimal(data.get("filled", 0))
        remaining = self._to_decimal(data.get("remaining", 0))
        cost = self._to_decimal(data.get("cost", 0))
        average = self._to_decimal(data.get("average"), allow_none=True)

        # 修正状态：如果订单已完全成交但状态不是filled，则更正为filled
        # 某些交易所(如Binance)对于市价单可能返回status=open但实际已成交
        if amount > 0 and filled >= amount and status not in ["filled", "closed"]:
            logger.debug(
                f"订单 {data.get('id')} 状态修正: {status} -> filled "
                f"(filled={filled}, amount={amount})"
            )
            status = "filled"
        fee = None
        if data.get("fee"):
            fee = self._to_decimal(data["fee"].get("cost"), allow_none=True)

        # 从多个可能的字段读取止损止盈价格
        # Binance API可能返回stopPrice, stopLossPrice, takeProfitPrice等
        # 同时也检查请求参数中的值（在info中）
        stop_price = self._to_decimal(
            data.get("stopPrice") or
            data.get("info", {}).get("stopPrice") or
            data.get("info", {}).get("activatePrice"),
            allow_none=True
        )
        take_profit_price = self._to_decimal(
            data.get("takeProfitPrice") or
            data.get("info", {}).get("takeProfitPrice"),
            allow_none=True
        )
        stop_loss_price = self._to_decimal(
            data.get("stopLossPrice") or
            data.get("info", {}).get("stopLossPrice"),
            allow_none=True
        )

        # 对于止损止盈订单，如果没有读取到专用价格字段，尝试使用stopPrice
        if not take_profit_price and order_type == OrderType.TAKE_PROFIT:
            take_profit_price = stop_price
        if not stop_loss_price and order_type == OrderType.STOP_LOSS:
            stop_loss_price = stop_price

        order = Order(
            id=str(data.get("id")),
            client_order_id=str(data.get("clientOrderId") or data.get("client_order_id") or data.get("id")),
            timestamp=timestamp or int(dt.timestamp() * 1000),
            dt=dt,
            symbol=data.get("symbol"),
            side=OrderSide(data.get("side", "buy")),
            type=order_type,
            status=OrderStatus(status if status in OrderStatus._value2member_map_ else "open"),
            price=price,
            amount=amount,
            filled=filled,
            remaining=remaining,
            cost=cost,
            average=average,
            fee=fee,
            stop_price=stop_price,
            take_profit_price=take_profit_price,
            stop_loss_price=stop_loss_price,
            exchange=self.exchange_id,
            info=data,
        )
        return order

    @staticmethod
    def _map_order_type(
        order_type: OrderType,
        price: Decimal | None = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        将内部订单类型映射为 CCXT 所需的类型字符串。

        对于 Binance 合约：
          - 市价止损/止盈需要使用 STOP_MARKET / TAKE_PROFIT_MARKET，并禁止携带 price。
          - 限价触发单需提供 price + stopPrice，类型为 STOP / TAKE_PROFIT。
        """
        params = params or {}
        has_price = price is not None
        has_stop_price = params.get("stopPrice") is not None

        if order_type == OrderType.MARKET:
            return "MARKET"
        if order_type == OrderType.LIMIT:
            return "LIMIT"

        if order_type == OrderType.STOP_LOSS:
            # Binance futures 止损单使用 STOP_MARKET (市价) 或 STOP (限价)
            return "stop_market" if not has_price else "stop"
        if order_type == OrderType.STOP_LOSS_LIMIT:
            return "stop" if has_stop_price else "stop"

        if order_type == OrderType.TAKE_PROFIT:
            # Binance futures 止盈单使用 TAKE_PROFIT_MARKET (市价) 或 TAKE_PROFIT (限价)
            return "take_profit_market" if not has_price else "take_profit"
        if order_type == OrderType.TAKE_PROFIT_LIMIT:
            return "take_profit" if has_stop_price else "take_profit"

        return "LIMIT"

    def _enable_sandbox_if_needed(self) -> None:
        """在配置支持的情况下启用 CCXT Sandbox/Testnet 模式"""
        if not self._exchange:
            return

        testnet_flag = bool(
            self.config.get("testnet")
            or self.config.get("sandboxMode")
            or self.config.get("options", {}).get("testnet")
        )
        exchange_id = getattr(self._exchange, "id", self.exchange_id)

        # Binance合约测试网：binance 和 binanceusdm 都使用testnet URL
        if testnet_flag and exchange_id in ("binance", "binanceusdm"):
            self._exchange.urls.setdefault("api", {})
            self._exchange.urls["api"].update(BINANCE_USDM_TESTNET_API.copy())
            self._exchange.isSandboxModeEnabled = False
            self._exchange.options = self._exchange.options or {}
            self._exchange.options["disableFuturesSandboxWarning"] = True
            logger.info("已切换 %s 到 Binance USDM 测试网接口", exchange_id)
            return

        if testnet_flag and hasattr(self._exchange, "set_sandbox_mode"):
            try:
                self._exchange.set_sandbox_mode(True)
                logger.info("Enabled sandbox mode for %s", self.exchange_id)
            except Exception as exc:  # pylint: disable=broad-except
                logger.warning(
                    "Failed to enable sandbox mode on %s: %s",
                    self.exchange_id,
                    exc,
                )
