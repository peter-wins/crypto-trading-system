"""
风险管理模块

实现标准风险检查逻辑，用于在下单前、持仓中以及组合层面进行限制校验。
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from src.core.logger import get_logger
from src.models.decision import TradingSignal, SignalType
from src.models.portfolio import Portfolio
from src.models.trade import OrderSide, Position


logger = get_logger(__name__)


class RiskCheckResult(BaseModel):
    """风险检查结果"""

    passed: bool = Field(..., description="风险检查是否通过")
    reason: Optional[str] = Field(None, description="未通过时的原因")
    suggested_adjustment: Optional[Dict[str, Any]] = Field(
        None, description="建议调整方案"
    )


DEFAULT_MAX_POSITION_SIZE = Decimal("0.2")
DEFAULT_MAX_DAILY_LOSS = Decimal("0.05")
DEFAULT_STOP_LOSS_PCT = Decimal("0.05")
DEFAULT_TAKE_PROFIT_PCT = Decimal("0.1")


class StandardRiskManager:
    """
    标准风险管理器。

    基于策略提供的风险参数进行仓位限制、止损止盈及熔断检查。
    """

    def __init__(self, *, circuit_breaker_threshold: Decimal = Decimal("0.3")) -> None:
        self.circuit_breaker_threshold = circuit_breaker_threshold

    async def check_order_risk(
        self,
        signal: TradingSignal,
        portfolio: Portfolio,
        risk_params: Dict[str, Decimal],
    ) -> RiskCheckResult:
        """
        检查下单风险，包括仓位占比、单日亏损限制和持仓方向冲突。
        """
        signal_type = signal.signal_type
        if signal_type in (SignalType.EXIT_LONG, SignalType.EXIT_SHORT):
            # 平仓/减仓属于降低风险行为，不受新增仓位限制
            return RiskCheckResult(passed=True)

        # 检查持仓方向冲突（开仓信号）
        if signal_type in (SignalType.ENTER_LONG, SignalType.ENTER_SHORT):
            existing_position = portfolio.get_position(signal.symbol)
            if existing_position:
                # 检查是否有反向持仓
                is_long_signal = signal_type == SignalType.ENTER_LONG
                is_long_position = existing_position.side == OrderSide.BUY

                if is_long_signal != is_long_position:
                    return RiskCheckResult(
                        passed=False,
                        reason=f"持仓方向冲突: 已有{'多头' if is_long_position else '空头'}持仓 {existing_position.amount}，"
                               f"但收到{'做多' if is_long_signal else '做空'}信号。请先平仓再开反向仓位。"
                    )
                else:
                    logger.info(
                        "%s 已有同方向持仓 %.4f，新信号将增加仓位",
                        signal.symbol, existing_position.amount
                    )

        max_position_size = risk_params.get("max_position_size", DEFAULT_MAX_POSITION_SIZE)
        max_daily_loss = risk_params.get("max_daily_loss", DEFAULT_MAX_DAILY_LOSS)
        suggested_amount = signal.suggested_amount
        suggested_price = signal.suggested_price

        if suggested_amount is None or suggested_price is None:
            return RiskCheckResult(
                passed=False,
                reason="缺少建议的下单数量或价格，无法进行风险评估",
            )

        # 检查杠杆倍数（从配置读取限制）
        leverage = signal.leverage or 1  # 默认1倍杠杆
        symbol = signal.symbol

        # 判断币种类型
        is_mainstream = any(coin in symbol.upper() for coin in ["BTC", "ETH"])

        # 从风险参数读取杠杆限制，如果没有则使用默认值
        max_leverage_mainstream = int(risk_params.get("max_leverage_mainstream", 50))
        max_leverage_altcoin = int(risk_params.get("max_leverage_altcoin", 20))
        max_leverage = max_leverage_mainstream if is_mainstream else max_leverage_altcoin

        if leverage < 1 or leverage > max_leverage:
            return RiskCheckResult(
                passed=False,
                reason=f"{symbol} 杠杆倍数 {leverage}x 超出允许范围 (1-{max_leverage}x)",
                suggested_adjustment={"suggested_leverage": min(max_leverage, max(1, leverage))},
            )

        # 高杠杆警告阈值（从配置读取，默认25x）
        high_leverage_warning = int(risk_params.get("high_leverage_warning", 25))
        if leverage > high_leverage_warning:
            logger.warning(
                "%s 使用高杠杆 %dx (超过警告阈值 %dx)，风险较大",
                symbol, leverage, high_leverage_warning
            )

        # 期货交易：计算名义价值和实际占用保证金
        notional_value = suggested_amount * suggested_price  # 名义价值
        margin_required = notional_value / Decimal(str(leverage))  # 实际占用保证金

        new_total = portfolio.total_value
        if new_total <= 0:
            return RiskCheckResult(
                passed=False,
                reason="组合总价值为零，无法下单",
            )

        allocation_pct = margin_required / new_total  # 使用保证金计算占比

        # 添加详细日志帮助调试
        logger.info(
            f"仓位检查 {symbol}: "
            f"名义价值={notional_value:.2f} USDT, "
            f"杠杆={leverage}x, "
            f"占用保证金={margin_required:.2f} USDT, "
            f"总资产={new_total:.2f} USDT, "
            f"占比={allocation_pct*100:.2f}%, "
            f"限制={max_position_size*100:.2f}%"
        )

        if allocation_pct > max_position_size:
            # 计算最大允许数量：(最大占比 × 总资产 × 杠杆) / 价格
            max_allowed = (max_position_size * new_total * Decimal(str(leverage))) / suggested_price
            logger.warning(
                f"仓位超限 {symbol}: 建议数量={suggested_amount:.4f}, "
                f"最大允许={max_allowed:.4f}, "
                f"建议价格={suggested_price:.2f}"
            )
            return RiskCheckResult(
                passed=False,
                reason="下单后仓位占比超出限制",
                suggested_adjustment={
                    "max_allowed_amount": max_allowed
                },
            )

        # 检查当日亏损
        if portfolio.daily_pnl < 0:
            daily_loss_pct = abs(portfolio.daily_pnl) / new_total
            if daily_loss_pct >= max_daily_loss:
                return RiskCheckResult(
                    passed=False,
                    reason="当日亏损已达到上限，触发风控熔断",
                )

        return RiskCheckResult(passed=True)

    async def check_position_risk(
        self,
        position: Position,
        current_price: Decimal,
    ) -> RiskCheckResult:
        """
        检查持仓风险，当价格触发止损/止盈时返回调整建议。
        """
        if position.side == OrderSide.BUY:
            if position.stop_loss and current_price <= position.stop_loss:
                return RiskCheckResult(
                    passed=False,
                    reason="价格跌破止损，应考虑平仓",
                    suggested_adjustment={"action": "close_position"},
                )
            if position.take_profit and current_price >= position.take_profit:
                return RiskCheckResult(
                    passed=False,
                    reason="达到止盈目标，可考虑锁定收益",
                    suggested_adjustment={"action": "take_profit"},
                )
        else:
            if position.stop_loss and current_price >= position.stop_loss:
                return RiskCheckResult(
                    passed=False,
                    reason="空头价格触发止损",
                    suggested_adjustment={"action": "close_position"},
                )
            if position.take_profit and current_price <= position.take_profit:
                return RiskCheckResult(
                    passed=False,
                    reason="空头达到止盈目标",
                    suggested_adjustment={"action": "take_profit"},
                )

        return RiskCheckResult(passed=True)

    async def check_portfolio_risk(self, portfolio: Portfolio) -> RiskCheckResult:
        """
        组合级别风险检查：若回撤超过阈值则触发熔断。
        """
        total_value = portfolio.total_value
        if total_value <= 0:
            return RiskCheckResult(
                passed=False,
                reason="组合价值为零，系统进入保护模式",
            )

        total_return = portfolio.total_return
        if total_return <= -self.circuit_breaker_threshold * Decimal("100"):
            return RiskCheckResult(
                passed=False,
                reason="组合累计回撤过大，触发熔断",
            )

        return RiskCheckResult(passed=True)

    async def calculate_stop_loss_take_profit(
        self,
        entry_price: Decimal,
        side: OrderSide,
        risk_params: Dict[str, Decimal],
    ) -> Dict[str, Decimal]:
        """
        根据风险参数计算止损与止盈价格。
        """
        stop_loss_pct = risk_params.get("stop_loss_percentage", DEFAULT_STOP_LOSS_PCT)
        take_profit_pct = risk_params.get(
            "take_profit_percentage", DEFAULT_TAKE_PROFIT_PCT
        )

        if entry_price <= 0:
            raise ValueError("Entry price must be positive")

        if side == OrderSide.BUY:
            stop_loss = entry_price * (Decimal("1") - stop_loss_pct / Decimal("100"))
            take_profit = entry_price * (Decimal("1") + take_profit_pct / Decimal("100"))
        else:
            stop_loss = entry_price * (Decimal("1") + stop_loss_pct / Decimal("100"))
            take_profit = entry_price * (Decimal("1") - take_profit_pct / Decimal("100"))

        logger.debug(
            "Calculated stop loss %.4f and take profit %.4f for entry %.4f",
            stop_loss,
            take_profit,
            entry_price,
        )

        return {
            "stop_loss": stop_loss.quantize(Decimal("0.0001")),
            "take_profit": take_profit.quantize(Decimal("0.0001")),
        }
