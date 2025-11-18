"""
交易相关模型

本模块定义订单、成交、持仓等交易相关的Pydantic模型。
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict, field_validator


class OrderSide(str, Enum):
    """订单方向"""
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    """订单类型"""
    MARKET = "market"
    LIMIT = "limit"
    STOP_LOSS = "stop_loss"
    STOP_LOSS_LIMIT = "stop_loss_limit"
    TAKE_PROFIT = "take_profit"
    TAKE_PROFIT_LIMIT = "take_profit_limit"


class OrderStatus(str, Enum):
    """订单状态"""
    PENDING = "pending"
    OPEN = "open"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELED = "canceled"
    REJECTED = "rejected"
    EXPIRED = "expired"


class Order(BaseModel):
    """订单模型"""

    model_config = ConfigDict(
        json_encoders={
            Decimal: str,
            datetime: lambda v: v.isoformat()
        }
    )

    id: str = Field(..., description="订单ID")
    client_order_id: str = Field(..., description="客户端订单ID")
    timestamp: int = Field(..., description="时间戳(毫秒)")
    dt: datetime = Field(..., description="时间")
    symbol: str = Field(..., description="交易对")
    side: OrderSide = Field(..., description="买卖方向")
    type: OrderType = Field(..., description="订单类型")
    status: OrderStatus = Field(..., description="订单状态")
    price: Optional[Decimal] = Field(None, description="价格(市价单为None)")
    amount: Decimal = Field(..., description="数量")
    filled: Decimal = Field(Decimal("0"), description="已成交数量")
    remaining: Decimal = Field(..., description="剩余数量")
    cost: Decimal = Field(Decimal("0"), description="成交金额")
    average: Optional[Decimal] = Field(None, description="平均成交价")
    fee: Optional[Decimal] = Field(None, description="手续费")

    # 止损止盈
    stop_price: Optional[Decimal] = Field(None, description="触发价格")
    take_profit_price: Optional[Decimal] = Field(None, description="止盈价格")
    stop_loss_price: Optional[Decimal] = Field(None, description="止损价格")

    # 额外信息
    exchange: str = Field(..., description="交易所")
    info: dict = Field(default_factory=dict, description="原始数据")


class Trade(BaseModel):
    """成交记录"""

    model_config = ConfigDict(
        json_encoders={
            Decimal: str,
            datetime: lambda v: v.isoformat()
        }
    )

    id: str = Field(..., description="成交ID")
    order_id: str = Field(..., description="订单ID")
    timestamp: int = Field(..., description="时间戳(毫秒)")
    dt: datetime = Field(..., description="时间")
    symbol: str = Field(..., description="交易对")
    side: OrderSide = Field(..., description="买卖方向")
    price: Decimal = Field(..., description="成交价格")
    amount: Decimal = Field(..., description="成交数量")
    cost: Decimal = Field(..., description="成交金额")
    fee: Optional[Decimal] = Field(None, description="手续费")
    fee_currency: Optional[str] = Field(None, description="手续费币种")
    info: dict = Field(default_factory=dict, description="原始数据")


class Position(BaseModel):
    """持仓信息"""

    model_config = ConfigDict(
        json_encoders={
            Decimal: str,
        }
    )

    symbol: str = Field(..., description="交易对")
    side: OrderSide = Field(..., description="持仓方向")
    amount: Decimal = Field(..., description="持仓数量")
    entry_price: Decimal = Field(..., description="平均成本价")
    current_price: Decimal = Field(..., description="当前价格")
    unrealized_pnl: Decimal = Field(..., description="未实现盈亏")
    unrealized_pnl_percentage: Decimal = Field(..., description="未实现盈亏比例(%)")
    value: Decimal = Field(..., description="持仓价值")

    # 风险指标
    stop_loss: Optional[Decimal] = Field(None, description="止损价格")
    take_profit: Optional[Decimal] = Field(None, description="止盈价格")
    liquidation_price: Optional[Decimal] = Field(None, description="强平价格")
    leverage: Optional[int] = Field(None, description="杠杆倍数")
    entry_fee: Optional[Decimal] = Field(None, description="开仓手续费")

    # 时间信息
    opened_at: Optional[int] = Field(None, description="开仓时间戳(毫秒)")

    def update_current_price(self, price: Decimal) -> None:
        """
        更新当前价格并重新计算盈亏

        Args:
            price: 新的当前价格
        """
        self.current_price = price
        self.value = self.amount * price

        if self.side == OrderSide.BUY:
            self.unrealized_pnl = (price - self.entry_price) * self.amount
        else:
            self.unrealized_pnl = (self.entry_price - price) * self.amount

        # 避免除以零
        if self.entry_price * self.amount != Decimal("0"):
            self.unrealized_pnl_percentage = (
                self.unrealized_pnl / (self.entry_price * self.amount) * Decimal("100")
            )
        else:
            self.unrealized_pnl_percentage = Decimal("0")
