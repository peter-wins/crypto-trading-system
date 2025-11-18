"""
决策模型

本模块定义交易信号、决策记录、策略配置等决策相关的Pydantic模型。
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, ConfigDict, field_validator


class SignalType(str, Enum):
    """信号类型"""
    ENTER_LONG = "enter_long"
    EXIT_LONG = "exit_long"
    ENTER_SHORT = "enter_short"
    EXIT_SHORT = "exit_short"
    HOLD = "hold"


class TradingSignal(BaseModel):
    """交易信号"""

    model_config = ConfigDict(
        json_encoders={
            Decimal: str,
            datetime: lambda v: v.isoformat()
        }
    )

    timestamp: int = Field(..., description="时间戳(毫秒)")
    dt: datetime = Field(..., description="时间")
    symbol: str = Field(..., description="交易对")
    signal_type: SignalType = Field(..., description="信号类型")
    confidence: float = Field(..., ge=0.0, le=1.0, description="信心分数 0-1")

    # 建议参数
    suggested_price: Optional[Decimal] = Field(None, description="建议价格")
    suggested_amount: Optional[Decimal] = Field(None, description="建议数量")
    stop_loss: Optional[Decimal] = Field(None, description="止损价格")
    take_profit: Optional[Decimal] = Field(None, description="止盈价格")
    leverage: Optional[int] = Field(None, ge=1, le=125, description="杠杆倍数 1-125x")

    # 理由
    reasoning: str = Field(..., description="信号产生理由")
    supporting_factors: List[str] = Field(default_factory=list, description="支持因素")
    risk_factors: List[str] = Field(default_factory=list, description="风险因素")

    # 来源
    source: str = Field(..., description="信号来源: strategist/trader")


class DecisionRecord(BaseModel):
    """决策记录"""

    model_config = ConfigDict(
        json_encoders={
            datetime: lambda v: v.isoformat()
        }
    )

    id: str = Field(..., description="决策ID")
    timestamp: int = Field(..., description="时间戳(毫秒)")
    dt: datetime = Field(..., description="时间")

    # 输入
    input_context: dict = Field(..., description="输入上下文")

    # 决策过程
    thought_process: str = Field(..., description="思考过程")
    tools_used: List[str] = Field(default_factory=list, description="使用的工具")

    # 输出
    decision: str = Field(..., description="最终决策")
    action_taken: Optional[str] = Field(None, description="采取的行动")

    # 元信息
    decision_layer: str = Field(..., description="决策层级: strategic/tactical")
    model_used: str = Field(..., description="使用的模型")
    tokens_used: Optional[int] = Field(None, description="消耗的token数")
    latency_ms: Optional[int] = Field(None, description="延迟(毫秒)")


class StrategyConfig(BaseModel):
    """策略配置"""

    model_config = ConfigDict(
        json_encoders={
            Decimal: str,
            datetime: lambda v: v.isoformat()
        }
    )

    name: str = Field(..., description="策略名称")
    version: str = Field(..., description="策略版本")
    description: str = Field(..., description="策略描述")

    # 交易参数
    max_position_size: Decimal = Field(..., description="最大仓位(占总资产比例)")
    max_single_trade: Decimal = Field(..., description="单笔最大交易额")
    max_open_positions: int = Field(..., description="最大持仓数量")

    # 风险参数
    max_daily_loss: Decimal = Field(..., description="最大日亏损(占总资产比例)")
    max_drawdown: Decimal = Field(..., description="最大回撤")
    stop_loss_percentage: Decimal = Field(..., description="止损比例")
    take_profit_percentage: Decimal = Field(..., description="止盈比例")

    # 市场参数
    trading_pairs: List[str] = Field(..., description="交易对列表")
    timeframes: List[str] = Field(..., description="时间周期")

    # 更新时间
    updated_at: datetime = Field(..., description="更新时间")
    reason_for_update: Optional[str] = Field(None, description="更新原因")
