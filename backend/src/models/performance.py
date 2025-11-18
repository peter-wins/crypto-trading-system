"""
绩效评估模型

本模块定义绩效指标、每日快照等性能评估相关的Pydantic模型。
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import List

from pydantic import BaseModel, Field, ConfigDict


class PerformanceMetrics(BaseModel):
    """绩效指标"""

    model_config = ConfigDict(
        json_encoders={
            Decimal: str,
            datetime: lambda v: v.isoformat()
        }
    )

    start_date: datetime = Field(..., description="开始日期")
    end_date: datetime = Field(..., description="结束日期")

    # 收益指标
    total_return: Decimal = Field(..., description="总收益率(%)")
    annualized_return: Decimal = Field(..., description="年化收益率(%)")
    daily_returns: List[Decimal] = Field(default_factory=list, description="每日收益率列表")

    # 风险指标
    volatility: Decimal = Field(..., description="波动率")
    max_drawdown: Decimal = Field(..., description="最大回撤(%)")
    sharpe_ratio: Decimal = Field(..., description="夏普比率")
    sortino_ratio: Decimal = Field(..., description="索提诺比率")
    calmar_ratio: Decimal = Field(..., description="卡尔玛比率")

    # 交易统计
    total_trades: int = Field(..., description="总交易次数")
    winning_trades: int = Field(..., description="盈利交易次数")
    losing_trades: int = Field(..., description="亏损交易次数")
    win_rate: Decimal = Field(..., description="胜率(%)")
    avg_win: Decimal = Field(..., description="平均盈利")
    avg_loss: Decimal = Field(..., description="平均亏损")
    profit_factor: Decimal = Field(..., description="盈亏比")

    # 其他
    max_consecutive_wins: int = Field(..., description="最大连续盈利次数")
    max_consecutive_losses: int = Field(..., description="最大连续亏损次数")


class DailySnapshot(BaseModel):
    """每日快照"""

    model_config = ConfigDict(
        json_encoders={
            Decimal: str,
            datetime: lambda v: v.isoformat()
        }
    )

    date: datetime = Field(..., description="日期")
    total_value: Decimal = Field(..., description="总价值")
    cash: Decimal = Field(..., description="现金")
    positions_value: Decimal = Field(..., description="持仓价值")
    daily_pnl: Decimal = Field(..., description="当日盈亏")
    daily_return: Decimal = Field(..., description="当日收益率(%)")
    drawdown: Decimal = Field(..., description="回撤(%)")
