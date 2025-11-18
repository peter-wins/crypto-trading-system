"""
记忆模型

本模块定义短期记忆（上下文）和长期记忆（经验）相关的Pydantic模型。
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field, ConfigDict

from .portfolio import Portfolio


class MarketContext(BaseModel):
    """市场上下文（短期记忆）"""

    model_config = ConfigDict(
        json_encoders={
            Decimal: str,
            datetime: lambda v: v.isoformat()
        }
    )

    timestamp: int = Field(..., description="时间戳(毫秒)")
    dt: datetime = Field(..., description="时间")

    # 市场状态
    market_regime: str = Field(..., description="市场状态: bull/bear/sideways")
    volatility: Decimal = Field(..., description="波动率")
    trend: str = Field(..., description="趋势: up/down/neutral")

    # 近期价格
    recent_prices: List[Decimal] = Field(default_factory=list, description="近期价格列表")

    # 技术指标
    indicators: dict = Field(default_factory=dict, description="技术指标字典")

    # 近期交易
    recent_trades: List[str] = Field(default_factory=list, description="近期交易ID列表")


class TradingContext(BaseModel):
    """交易上下文"""

    model_config = ConfigDict(
        json_encoders={
            Decimal: str,
            datetime: lambda v: v.isoformat()
        }
    )

    timestamp: int = Field(..., description="时间戳(毫秒)")
    dt: datetime = Field(..., description="时间")

    # 当前策略
    current_strategy: str = Field(..., description="当前策略名称")
    strategy_params: dict = Field(default_factory=dict, description="策略参数")

    # 风险参数
    max_position_size: Decimal = Field(..., description="最大仓位比例")
    max_daily_loss: Decimal = Field(..., description="最大日亏损比例")
    current_daily_loss: Decimal = Field(Decimal("0"), description="当前日亏损")

    # 市场上下文
    market_context: MarketContext = Field(..., description="市场上下文")

    # 投资组合
    portfolio: Portfolio = Field(..., description="投资组合")


class TradingExperience(BaseModel):
    """交易经验（长期记忆）"""

    model_config = ConfigDict(
        json_encoders={
            Decimal: str,
            datetime: lambda v: v.isoformat()
        }
    )

    id: str = Field(..., description="经验ID")
    timestamp: int = Field(..., description="时间戳(毫秒)")
    dt: datetime = Field(..., description="时间")

    # 情景描述
    situation: str = Field(..., description="市场情况描述")
    situation_embedding: Optional[List[float]] = Field(None, description="向量表示")

    # 决策
    decision: str = Field(..., description="做出的决策")
    decision_reasoning: str = Field(..., description="决策理由")

    # 结果
    outcome: str = Field(..., description="结果: success/failure")
    pnl: Decimal = Field(..., description="盈亏")
    pnl_percentage: Decimal = Field(..., description="盈亏比例(%)")

    # 反思
    reflection: Optional[str] = Field(None, description="事后反思")
    lessons_learned: List[str] = Field(default_factory=list, description="经验教训")

    # 元数据
    tags: List[str] = Field(default_factory=list, description="标签")
    importance_score: float = Field(0.0, description="重要性评分 0-1")


class MemoryQuery(BaseModel):
    """记忆查询请求"""

    model_config = ConfigDict(json_encoders={})

    query_text: str = Field(..., description="查询文本")
    query_embedding: Optional[List[float]] = Field(None, description="查询向量")
    top_k: int = Field(5, description="返回前K个结果")
    filters: dict = Field(default_factory=dict, description="过滤条件")
    min_importance: float = Field(0.0, description="最小重要性分数")
