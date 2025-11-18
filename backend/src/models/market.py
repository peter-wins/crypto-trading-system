"""
市场数据模型

本模块定义市场数据相关的Pydantic模型。
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import List

from pydantic import BaseModel, Field, ConfigDict


class OHLCVData(BaseModel):
    """K线数据模型"""

    model_config = ConfigDict(
        json_encoders={
            Decimal: str,
            datetime: lambda v: v.isoformat()
        }
    )

    symbol: str = Field(..., description="交易对，如BTC/USDT")
    timestamp: int = Field(..., description="时间戳(毫秒)")
    dt: datetime = Field(..., description="时间")
    open: Decimal = Field(..., description="开盘价")
    high: Decimal = Field(..., description="最高价")
    low: Decimal = Field(..., description="最低价")
    close: Decimal = Field(..., description="收盘价")
    volume: Decimal = Field(..., description="成交量")


class OrderBookLevel(BaseModel):
    """订单簿单层数据"""

    model_config = ConfigDict(json_encoders={Decimal: str})

    price: Decimal = Field(..., description="价格")
    amount: Decimal = Field(..., description="数量")


class OrderBook(BaseModel):
    """完整订单簿"""

    model_config = ConfigDict(
        json_encoders={
            Decimal: str,
            datetime: lambda v: v.isoformat()
        }
    )

    symbol: str = Field(..., description="交易对")
    timestamp: int = Field(..., description="时间戳(毫秒)")
    dt: datetime = Field(..., description="时间")
    bids: List[OrderBookLevel] = Field(..., description="买单列表，按价格降序")
    asks: List[OrderBookLevel] = Field(..., description="卖单列表，按价格升序")

    def get_spread(self) -> Decimal:
        """获取买卖价差"""
        if not self.bids or not self.asks:
            return Decimal("0")
        return self.asks[0].price - self.bids[0].price

    def get_mid_price(self) -> Decimal:
        """获取中间价"""
        if not self.bids or not self.asks:
            return Decimal("0")
        return (self.asks[0].price + self.bids[0].price) / Decimal("2")


class Ticker(BaseModel):
    """Ticker数据"""

    model_config = ConfigDict(
        json_encoders={
            Decimal: str,
            datetime: lambda v: v.isoformat()
        }
    )

    symbol: str = Field(..., description="交易对")
    timestamp: int = Field(..., description="时间戳(毫秒)")
    dt: datetime = Field(..., description="时间")
    last: Decimal = Field(..., description="最新成交价")
    bid: Decimal = Field(..., description="最佳买价")
    ask: Decimal = Field(..., description="最佳卖价")
    high: Decimal = Field(..., description="24h最高价")
    low: Decimal = Field(..., description="24h最低价")
    volume: Decimal = Field(..., description="24h成交量")
    quote_volume: Decimal = Field(..., description="24h成交额")
    change_24h: Decimal = Field(..., description="24h涨跌幅(%)")
