#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Trading Execution Service

交易执行服务,负责处理交易信号、执行订单、管理风险。
将交易执行逻辑从主系统中分离,提高代码的可维护性和可测试性。
"""

import logging
from decimal import Decimal
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from src.models.decision import TradingSignal, StrategyConfig, SignalType
from src.models.portfolio import Portfolio
from src.models.trade import Order, OrderSide, OrderType
from src.models.memory import TradingContext
from src.execution.order import CCXTOrderExecutor
from src.execution.risk import StandardRiskManager
from src.execution.portfolio import PortfolioManager
from src.memory.short_term import RedisShortTermMemory
from src.services.database import DatabaseManager
from src.services.database import TradingDAO
from src.core.config import RiskConfig
from src.core.exceptions import TradingSystemError


class TradingExecutor:
    """
    交易执行服务

    职责:
    1. 处理交易信号 (信号验证、仓位检查、止盈止损计算)
    2. 执行订单 (下单、止损止盈单、保护单)
    3. 管理风险 (风控校验)
    4. 更新交易上下文 (Redis)
    5. 持久化数据 (数据库)
    """

    def __init__(
        self,
        order_executor: CCXTOrderExecutor,
        risk_manager: StandardRiskManager,
        portfolio_manager: PortfolioManager,
        short_term_memory: Optional[RedisShortTermMemory] = None,
        db_manager: Optional[DatabaseManager] = None,
        risk_config: Optional[RiskConfig] = None,
        symbol_mapper: Optional[Any] = None,
        enable_trading: bool = False,
        logger: Optional[logging.Logger] = None,
    ):
        """
        初始化交易执行服务

        Args:
            order_executor: 订单执行器
            risk_manager: 风险管理器
            portfolio_manager: 投资组合管理器
            short_term_memory: 短期内存 (Redis)
            db_manager: 数据库管理器
            risk_config: 风险配置
            symbol_mapper: 交易对映射器
            enable_trading: 是否启用真实交易
            logger: 日志记录器
        """
        self.order_executor = order_executor
        self.risk_manager = risk_manager
        self.portfolio_manager = portfolio_manager
        self.short_term_memory = short_term_memory
        self.db_manager = db_manager
        self.risk_config = risk_config
        self.symbol_mapper = symbol_mapper
        self.enable_trading = enable_trading
        self.logger = logger or logging.getLogger(__name__)

    async def process_trading_signal(
        self,
        symbol: str,
        signal: TradingSignal,
        strategy: StrategyConfig,
        snapshot: Dict[str, Any],
        portfolio: Portfolio,
    ) -> Optional[Portfolio]:
        """
        处理交易信号的完整流程

        Args:
            symbol: 交易对符号
            signal: 交易信号
            strategy: 策略配置
            snapshot: 市场数据快照
            portfolio: 当前投资组合

        Returns:
            执行后的最新组合（成功）或 None（失败/被拒绝）
        """
        try:
            # 1. 验证和调整信号参数
            if not self._validate_and_adjust_signal(symbol, signal, snapshot, portfolio):
                await self._update_trading_context(symbol, strategy, portfolio, snapshot)
                return None

            # 2. 风控校验
            if not await self._check_risk(symbol, signal, portfolio):
                await self._update_trading_context(symbol, strategy, portfolio, snapshot)
                return None

            # 3. 计算止盈止损
            entry_price = signal.suggested_price or Decimal(str(snapshot["latest_price"]))
            side = self._determine_order_side(signal)
            await self._calculate_stops_if_needed(symbol, signal, entry_price, side)

            # 4. 执行信号
            updated_portfolio = await self._execute_signal(
                symbol, signal, strategy, side, entry_price, snapshot, portfolio
            )

            return updated_portfolio

        except Exception as exc:
            self.logger.error("处理交易信号时发生错误: %s", exc, exc_info=True)
            return None

    def _validate_and_adjust_signal(
        self,
        symbol: str,
        signal: TradingSignal,
        snapshot: Dict[str, Any],
        portfolio: Portfolio,
    ) -> bool:
        """
        验证和调整信号参数

        Returns:
            True=信号有效, False=信号无效应忽略
        """
        position_side = self._position_side_for_signal(signal)

        # 对于平仓信号,检查是否有持仓
        if signal.signal_type in [SignalType.EXIT_LONG, SignalType.EXIT_SHORT]:
            current_position = portfolio.get_position(symbol, position_side)
            if not current_position:
                self.logger.warning("%s 无持仓，平仓信号已忽略：%s", symbol, signal.signal_type.value)
                return False

            # 如果LLM没有指定平仓数量,默认使用全部持仓
            if signal.suggested_amount is None:
                signal.suggested_amount = current_position.amount
                self.logger.info(
                    "%s LLM未指定平仓数量，默认全部平仓：%s (持仓总量：%s)",
                    symbol, signal.suggested_amount, current_position.amount
                )
            else:
                # LLM指定了数量,检查是否合理
                if signal.suggested_amount > current_position.amount:
                    self.logger.warning(
                        "%s LLM建议平仓数量 %s 超过持仓 %s，调整为全部平仓",
                        symbol, signal.suggested_amount, current_position.amount
                    )
                    signal.suggested_amount = current_position.amount
                else:
                    percentage = (signal.suggested_amount / current_position.amount * 100)
                    self.logger.info(
                        "%s LLM决定部分平仓：%s (%.1f%% 持仓，剩余：%s)",
                        symbol, signal.suggested_amount, percentage,
                        current_position.amount - signal.suggested_amount
                    )

            # 自动使用当前市价
            if signal.suggested_price is None:
                signal.suggested_price = Decimal(str(snapshot["latest_price"]))
                self.logger.debug("%s 平仓使用当前市价：%s", symbol, signal.suggested_price)

        # 对于开仓信号,必须有建议数量和价格
        elif signal.signal_type in [SignalType.ENTER_LONG, SignalType.ENTER_SHORT]:
            if signal.suggested_amount is None or signal.suggested_price is None:
                self.logger.warning(
                    "%s 开仓信号缺少建议数量或价格，已忽略：%s",
                    symbol,
                    signal.signal_type.value,
                )
                return False

        return True

    async def _check_risk(
        self,
        symbol: str,
        signal: TradingSignal,
        portfolio: Portfolio,
    ) -> bool:
        """
        风控校验

        Returns:
            True=通过, False=未通过
        """
        risk_params = self._get_risk_params()
        risk_result = await self.risk_manager.check_order_risk(signal, portfolio, risk_params)

        if not risk_result.passed:
            self.logger.warning("%s 风控未通过，原因：%s", symbol, risk_result.reason)
            return False

        return True

    async def _calculate_stops_if_needed(
        self,
        symbol: str,
        signal: TradingSignal,
        entry_price: Decimal,
        side: OrderSide,
    ) -> None:
        """计算止盈止损 (如果LLM没有设置的话)"""
        if signal.signal_type in (SignalType.EXIT_LONG, SignalType.EXIT_SHORT):
            signal.stop_loss = None
            signal.take_profit = None
            self.logger.debug("%s 平仓信号，跳过止盈/止损计算", symbol)
            return

        # 尊重LLM的自主决策：只有在LLM没有设置止盈止损时,才使用风控模块的默认值
        if signal.stop_loss is None or signal.take_profit is None:
            risk_params = self._get_risk_params()
            stops = await self.risk_manager.calculate_stop_loss_take_profit(
                entry_price, side, risk_params
            )

            if signal.stop_loss is None:
                signal.stop_loss = stops["stop_loss"]
                self.logger.debug(
                    "%s LLM未设置止损，使用风控默认值：%s",
                    symbol, signal.stop_loss
                )
            else:
                self.logger.info(
                    "%s 使用LLM决策的止损：%s (风控建议：%s)",
                    symbol, signal.stop_loss, stops["stop_loss"]
                )

            if signal.take_profit is None:
                signal.take_profit = stops["take_profit"]
                self.logger.debug(
                    "%s LLM未设置止盈，使用风控默认值：%s",
                    symbol, signal.take_profit
                )
            else:
                self.logger.info(
                    "%s 使用LLM决策的止盈：%s (风控建议：%s)",
                    symbol, signal.take_profit, stops["take_profit"]
                )
        # LLM已设置止盈止损，无需额外日志

    async def _execute_signal(
        self,
        data_symbol: str,
        signal: TradingSignal,
        strategy: StrategyConfig,
        side: OrderSide,
        entry_price: Decimal,
        snapshot: Dict[str, Any],
        portfolio: Portfolio,
    ) -> None:
        """
        执行交易信号 (下单、更新组合、保存数据)

        Args:
            data_symbol: 数据源的交易对
            signal: 交易信号
            strategy: 策略配置
            side: 订单方向
            entry_price: 入场价格
            snapshot: 市场数据快照
            portfolio: 当前投资组合
        """
        # 映射交易对符号
        trading_symbol = self._map_symbol_for_trading(data_symbol)

        position_side = self._position_side_for_signal(signal)

        pre_position = None
        if signal.signal_type in (SignalType.EXIT_LONG, SignalType.EXIT_SHORT):
            pre_position = portfolio.get_position(data_symbol, position_side)

        amount = signal.suggested_amount
        if amount is None or amount <= Decimal("0"):
            self.logger.info("%s 信号数量无效，忽略。", trading_symbol)
            if self.portfolio_manager:
                portfolio = await self.portfolio_manager.get_current_portfolio()
                await self._update_trading_context(data_symbol, strategy, portfolio, snapshot)
            return

        if signal.signal_type in (SignalType.EXIT_LONG, SignalType.EXIT_SHORT):
            await self._cancel_existing_protection_orders(trading_symbol)

        # 合并杠杆和下单信息到一个日志
        leverage_info = f" 杠杆={signal.leverage}x" if signal.leverage else ""
        self.logger.info(
            "%s 下单：%s %s @ %s%s 止损=%s 止盈=%s",
            trading_symbol,
            self._describe_order_direction(signal.signal_type, side),
            amount,
            entry_price,
            leverage_info,
            signal.stop_loss or "无",
            signal.take_profit or "无",
        )

        # 检查是否重复操作
        if await self._is_duplicate_action(trading_symbol, signal, amount):
            await self._update_trading_context(data_symbol, strategy, portfolio, snapshot)
            return

        # 创建订单
        order_group = await self._create_orders(trading_symbol, signal, side, amount)
        order = order_group["main"]

        # 保存订单到数据库
        await self._save_orders_to_db(order_group)

        # 更新投资组合
        updated_portfolio = await self._update_portfolio(
            trading_symbol, side, order, entry_price
        )

        # 创建保护单 (平仓后的剩余仓位)
        if signal.signal_type in (SignalType.EXIT_LONG, SignalType.EXIT_SHORT):
            await self._create_protective_orders_if_needed(
                trading_symbol, signal, snapshot, updated_portfolio, order_group
            )
            await self._register_expected_close(
                data_symbol,
                position_side,
                pre_position,
                signal,
                order,
                entry_price,
            )

        # 更新交易上下文
        await self._update_trading_context(data_symbol, strategy, updated_portfolio, snapshot)

        return updated_portfolio

    async def _is_duplicate_action(
        self,
        symbol: str,
        signal: TradingSignal,
        amount: Decimal,
    ) -> bool:
        """检查是否是重复的平仓操作"""
        if (
            signal.signal_type in (SignalType.EXIT_LONG, SignalType.EXIT_SHORT)
            and self.short_term_memory
        ):
            last_action = await self.short_term_memory.get_last_trade_action(symbol)
            if last_action and last_action.get("signal_type") == signal.signal_type.value:
                try:
                    last_time = datetime.fromisoformat(last_action.get("timestamp"))
                except Exception:  # pylint: disable=broad-except
                    last_time = None

                last_amount = Decimal(str(last_action.get("amount", "0")))
                now = datetime.now(timezone.utc)
                recently = (
                    last_time is not None
                    and (now - last_time).total_seconds() < 600
                )

                if recently and abs(last_amount - amount) <= Decimal("0.0001"):
                    self.logger.info(
                        "%s 已在近期执行相同的平仓动作（数量=%s），跳过重复操作。",
                        symbol,
                        amount,
                    )
                    return True

        return False

    async def _create_orders(
        self,
        symbol: str,
        signal: TradingSignal,
        side: OrderSide,
        amount: Decimal,
    ) -> Dict[str, Order]:
        """
        创建订单 (主订单 + 止损止盈单)

        Returns:
            订单组字典 {"main": Order, "stop_loss": Order, "take_profit": Order}
        """
        # Exit 信号：先市场减仓
        if signal.signal_type in (SignalType.EXIT_LONG, SignalType.EXIT_SHORT):
            order = await self.order_executor.create_order(
                symbol=symbol,
                side=side,
                order_type=OrderType.MARKET,
                amount=amount,
                price=None,
                reduceOnly=True,
            )
            return {"main": order}
        else:
            # 开仓信号：创建带止损止盈的订单
            return await self.order_executor.create_order_with_stops(
                symbol=symbol,
                side=side,
                amount=amount,
                price=None,  # 市价单
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profit,
                leverage=signal.leverage,  # LLM 决定的杠杆倍数
            )

    def _describe_order_direction(self, signal_type: SignalType, side: OrderSide) -> str:
        if signal_type == SignalType.EXIT_SHORT:
            return "买入(平空)"
        if signal_type == SignalType.EXIT_LONG:
            return "卖出(平多)"
        return "买入" if side == OrderSide.BUY else "卖出"

    async def _cancel_existing_protection_orders(self, symbol: str) -> None:
        """撤销已有的止盈/止损保护单，避免平仓后残留。"""
        if not self.order_executor:
            return

        try:
            open_orders = await self.order_executor.get_open_orders(symbol)
        except Exception as exc:  # pylint: disable=broad-except
            self.logger.debug("%s 获取未完成订单失败，无法自动撤销保护单: %s", symbol, exc)
            return

        protective_types = {
            OrderType.STOP_LOSS,
            OrderType.STOP_LOSS_LIMIT,
            OrderType.TAKE_PROFIT,
            OrderType.TAKE_PROFIT_LIMIT,
        }

        candidates = []
        for order in open_orders:
            info = order.info or {}
            close_position_flag = str(info.get("closePosition", "")).lower() == "true"
            if close_position_flag or order.type in protective_types:
                candidates.append(order)

        if not candidates:
            return

        for order in candidates:
            try:
                await self.order_executor.cancel_order(order.id, symbol)
                self.logger.info("%s 已撤销保护单 %s (%s)", symbol, order.id, order.type.value)
            except Exception as exc:  # pylint: disable=broad-except
                self.logger.warning("%s 保护单 %s 撤销失败: %s", symbol, order.id, exc)

    async def _save_orders_to_db(self, order_group: Dict[str, Order]) -> None:
        """保存所有订单到数据库"""
        if not self.db_manager:
            return

        try:
            async with self.db_manager.get_session() as session:
                dao = TradingDAO(session)
                # 保存主订单
                await dao.save_order(order_group["main"])
                # 保存止损订单
                if "stop_loss" in order_group:
                    await dao.save_order(order_group["stop_loss"])
                # 保存止盈订单
                if "take_profit" in order_group:
                    await dao.save_order(order_group["take_profit"])

                # 保存成交明细（如果主订单已成交）
                await self._fetch_and_save_trades(order_group["main"], dao)

        except Exception as exc:
            self.logger.warning("保存订单到数据库失败: %s", exc)

    async def _fetch_and_save_trades(self, order: Order, dao: TradingDAO) -> None:
        """
        获取并保存订单的成交明细

        Args:
            order: 订单对象
            dao: 数据访问对象
        """
        from src.models.trade import Trade, OrderStatus

        # 只有有成交数量的订单才拉取trades
        # 注意：某些交易所返回的订单状态可能不准确，以filled数量为准
        if not order.filled or order.filled == 0:
            self.logger.debug(
                f"订单 {order.id} 无成交数量 (filled={order.filled})，跳过成交记录保存"
            )
            return

        try:
            self.logger.debug(f"开始获取订单 {order.id} 的成交记录...")

            # 1. 尝试从订单info中获取trades
            trades_data = order.info.get("trades", [])
            if trades_data:
                self.logger.debug(f"从订单info中找到 {len(trades_data)} 条成交记录")

            # 2. 如果info中没有trades，且不是纸面交易，则主动拉取
            if not trades_data and not self.order_executor.paper_trading:
                self.logger.debug("尝试从交易所API拉取成交记录...")
                try:
                    # 币安合约使用 fetch_my_trades，然后筛选属于此订单的记录
                    from src.services.exchange import get_exchange_service
                    exchange_service = get_exchange_service()
                    all_trades = await exchange_service.fetch_my_trades(
                        symbol=order.symbol,
                        limit=100  # 获取最近100笔成交
                    )
                    # 筛选属于此订单的成交记录
                    trades_data = [t for t in all_trades if str(t.get('order')) == str(order.id)]
                    self.logger.debug(f"从交易所API拉取到 {len(trades_data)} 条成交记录 (订单 {order.id})")
                except Exception as exc:
                    self.logger.debug("无法拉取订单trades: %s", exc)
                    trades_data = []

            # 3. 如果仍然没有trades，但订单已成交，则根据订单信息生成trade记录
            if not trades_data and order.filled and order.filled > 0:
                self.logger.debug(
                    f"订单 {order.id} 无法获取trades，根据订单信息生成合成trade记录"
                )
                # 生成合成的trade数据
                synthetic_trade = {
                    "id": f"{order.id}_synthetic",
                    "order": order.id,
                    "timestamp": order.timestamp,
                    "datetime": order.dt.isoformat(),
                    "symbol": order.symbol,
                    "type": order.type.value,
                    "side": order.side.value,
                    "price": float(order.average) if order.average else float(order.price) if order.price else 0,
                    "amount": float(order.filled),
                    "cost": float(order.cost) if order.cost else 0,
                    "fee": {
                        "cost": float(order.fee) if order.fee else 0,
                        "currency": order.fee_currency if hasattr(order, 'fee_currency') else "USDT"
                    },
                    "info": order.info
                }
                trades_data = [synthetic_trade]
                self.logger.info(
                    f"生成合成trade: {order.symbol} {order.side.value} "
                    f"@ {synthetic_trade['price']}, 数量={synthetic_trade['amount']}"
                )

            if not trades_data:
                self.logger.info(
                    f"订单 {order.id} 无成交记录且未成交任何数量 (纸面交易={self.order_executor.paper_trading})"
                )
                return

            # 3. 转换并保存trades
            saved_count = 0
            for idx, trade_data in enumerate(trades_data, 1):
                trade = self._convert_trade(trade_data, order)
                success = await dao.save_trade(trade, exchange_name=order.exchange)
                if success:
                    saved_count += 1
                    self.logger.info(
                        f"✓ [{idx}/{len(trades_data)}] 保存成交记录: {trade.id} | "
                        f"{trade.symbol} {trade.side.value} @ {trade.price}, "
                        f"数量={trade.amount}, 手续费={trade.fee} {trade.fee_currency}"
                    )
                else:
                    self.logger.warning(f"✗ [{idx}/{len(trades_data)}] 成交记录 {trade.id} 保存失败")

            self.logger.info(f"✅ 订单 {order.id} 成交记录保存完成: {saved_count}/{len(trades_data)}")

        except Exception as exc:
            self.logger.warning("获取并保存trades失败: %s", exc, exc_info=True)

    def _convert_trade(self, data: Dict[str, Any], order: Order) -> "Trade":
        """
        将CCXT trade数据转换为Trade模型

        Args:
            data: CCXT返回的trade数据
            order: 关联的订单

        Returns:
            Trade对象
        """
        from src.models.trade import Trade
        from datetime import datetime, timezone
        from decimal import Decimal

        # 解析时间戳
        timestamp = data.get("timestamp") or data.get("datetime")
        if isinstance(timestamp, str):
            try:
                dt_obj = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                timestamp = int(dt_obj.timestamp() * 1000)
            except ValueError:
                timestamp = int(datetime.now(timezone.utc).timestamp() * 1000)
        elif timestamp is None:
            timestamp = int(datetime.now(timezone.utc).timestamp() * 1000)

        dt = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)

        # 解析手续费
        fee = None
        fee_currency = None
        if data.get("fee"):
            fee = Decimal(str(data["fee"].get("cost", 0)))
            fee_currency = data["fee"].get("currency")

        trade = Trade(
            id=str(data.get("id", data.get("trade_id", str(timestamp)))),
            order_id=order.id,
            timestamp=timestamp,
            dt=dt,
            symbol=data.get("symbol", order.symbol),
            side=order.side,
            price=Decimal(str(data.get("price", 0))),
            amount=Decimal(str(data.get("amount", 0))),
            cost=Decimal(str(data.get("cost", 0))),
            fee=fee,
            fee_currency=fee_currency,
            info=data,
        )

        return trade

    async def _update_portfolio(
        self,
        symbol: str,
        side: OrderSide,
        order: Order,
        entry_price: Decimal,
    ) -> Portfolio:
        """更新投资组合"""
        fill_price = order.average or order.price or entry_price
        filled_amount = order.filled if order.filled > 0 else order.amount

        # 纸面交易模式：手动应用成交
        if not self.enable_trading:
            self.portfolio_manager.apply_fill(symbol, side, filled_amount, fill_price)

        # 更新组合
        if self.enable_trading:
            return await self.portfolio_manager.update_portfolio()
        else:
            return await self.portfolio_manager.get_current_portfolio()

    async def _create_protective_orders_if_needed(
        self,
        symbol: str,
        signal: TradingSignal,
        snapshot: Dict[str, Any],
        portfolio: Portfolio,
        order_group: Dict[str, Order],
    ) -> None:
        """为平仓后的剩余仓位创建保护单"""
        if (
            signal.signal_type in (SignalType.EXIT_LONG, SignalType.EXIT_SHORT)
            and (signal.stop_loss or signal.take_profit)
        ):
            remaining_position = portfolio.get_position(
                symbol,
                self._position_side_for_signal(signal),
            )
            if remaining_position and remaining_position.amount > Decimal("0"):
                remaining_price = remaining_position.current_price or Decimal(str(snapshot["latest_price"]))
                protective = await self.order_executor.create_protective_orders(
                    symbol=symbol,
                    position_side=remaining_position.side,
                    amount=remaining_position.amount,
                    current_price=remaining_price,
                    stop_loss=signal.stop_loss,
                    take_profit=signal.take_profit,
                )
                order_group.update(protective)

    async def _register_expected_close(
        self,
        symbol: str,
        position_side: Optional[OrderSide],
        pre_position: Optional["Position"],
        signal: TradingSignal,
        order: Order,
        fallback_price: Decimal,
    ) -> None:
        """通知 AccountSyncService 预计的平仓结果"""
        if (
            signal.signal_type not in (SignalType.EXIT_LONG, SignalType.EXIT_SHORT)
            or not self.portfolio_manager
            or not position_side
            or not pre_position
        ):
            return

        account_sync = getattr(self.portfolio_manager, "account_sync_service", None)
        if not account_sync:
            return

        # 优先使用订单的实际成交价，其次使用下单时的市价快照 (fallback_price)
        # 注意：千万不要使用 pre_position.current_price，那是开仓价不是平仓价！
        exit_price = order.average or order.price or fallback_price
        if exit_price is None:
            # 如果都没有，使用当前市价作为最后兜底
            exit_price = fallback_price
        exit_price = Decimal(str(exit_price))

        timestamp = order.timestamp or int(datetime.now(timezone.utc).timestamp() * 1000)
        exit_time = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)

        filled_amount = order.filled if order.filled > Decimal("0") else order.amount
        closed_amount = min(pre_position.amount, filled_amount)

        try:
            close_reason = "manual" if signal.signal_type in (SignalType.EXIT_LONG, SignalType.EXIT_SHORT) else "system"
            account_sync.register_expected_close(
                symbol=symbol,
                side=position_side,
                amount=closed_amount,
                exit_price=exit_price,
                exit_time=exit_time,
                order_id=order.id,
                reason=close_reason,
            )
        except Exception as exc:  # pylint: disable=broad-except
            self.logger.debug("登记预期平仓失败 %s: %s", symbol, exc)

    async def _update_trading_context(
        self,
        symbol: str,
        strategy: StrategyConfig,
        portfolio: Portfolio,
        snapshot: Dict[str, Any],
    ) -> None:
        """更新交易上下文到 Redis"""
        if not self.short_term_memory:
            return

        now = datetime.now(timezone.utc)

        # 处理market_context字段
        # 新格式: snapshot只有market_summary字段,需要创建简单的MarketContext
        # 旧格式: snapshot包含完整的market_context对象
        if "market_context" in snapshot:
            market_context = snapshot["market_context"]
        else:
            # 从新格式snapshot创建简单的MarketContext
            from src.models.memory import MarketContext
            market_context = MarketContext(
                timestamp=int(now.timestamp() * 1000),
                dt=now,
                market_regime="unknown",  # 简化版本没有这个信息
                volatility=Decimal("0"),
                trend="neutral",
                recent_prices=[snapshot.get("latest_price", Decimal("0"))],
                indicators={"summary": snapshot.get("market_summary", "")},
                recent_trades=[],
            )

        trading_context = TradingContext(
            timestamp=int(now.timestamp() * 1000),
            dt=now,
            current_strategy=strategy.name,
            strategy_params={
                "description": strategy.description,
                "pairs": strategy.trading_pairs,
                "timeframes": strategy.timeframes,
            },
            max_position_size=self.risk_config.max_position_size if self.risk_config else Decimal("0.2"),
            max_daily_loss=self.risk_config.max_daily_loss if self.risk_config else Decimal("0.05"),
            current_daily_loss=portfolio.daily_pnl,
            market_context=market_context,
            portfolio=portfolio,
        )
        await self.short_term_memory.update_trading_context(trading_context)

    def _get_risk_params(self) -> Dict[str, Decimal]:
        """获取风险参数"""
        if self.risk_config:
            return {
                "max_position_size": self.risk_config.max_position_size,
                "max_daily_loss": self.risk_config.max_daily_loss,
                "max_drawdown": self.risk_config.max_drawdown,
                "stop_loss_percentage": Decimal(str(self.risk_config.stop_loss_percentage)),
                "take_profit_percentage": Decimal(str(self.risk_config.take_profit_percentage)),
            }
        else:
            # 默认值
            return {
                "max_position_size": Decimal("0.2"),
                "max_daily_loss": Decimal("0.05"),
                "max_drawdown": Decimal("0.15"),
                "stop_loss_percentage": Decimal("5.0"),
                "take_profit_percentage": Decimal("10.0"),
            }

    def _determine_order_side(self, signal: TradingSignal) -> OrderSide:
        """根据信号类型确定订单方向"""
        if signal.signal_type in (SignalType.ENTER_LONG, SignalType.EXIT_SHORT):
            return OrderSide.BUY
        else:
            return OrderSide.SELL

    def _position_side_for_signal(self, signal: TradingSignal) -> Optional[OrderSide]:
        """获取与信号对应的持仓方向"""
        if signal.signal_type in (SignalType.ENTER_LONG, SignalType.EXIT_LONG):
            return OrderSide.BUY
        if signal.signal_type in (SignalType.ENTER_SHORT, SignalType.EXIT_SHORT):
            return OrderSide.SELL
        return None

    def _map_symbol_for_trading(self, data_symbol: str) -> str:
        """
        将数据源的交易对映射到交易所交易对

        Args:
            data_symbol: 数据源交易对 (如 BTC/USDC:USDC)

        Returns:
            交易所交易对 (如 BTC/USDT)
        """
        if self.symbol_mapper:
            return self.symbol_mapper.map(data_symbol)
        return data_symbol
