"""
Market Regime Models

定义战略层(Strategist)输出的市场状态判断数据结构
"""

from __future__ import annotations

from enum import Enum
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class MarketBias(str, Enum):
    """市场偏向"""

    BULLISH = "bullish"   # 偏多
    BEARISH = "bearish"   # 偏空
    NEUTRAL = "neutral"   # 中性


class MarketStructure(str, Enum):
    """市场结构/环境类型"""

    TRENDING = "trending"     # 趋势
    RANGING = "ranging"       # 震荡
    EXTREME_VOL = "extreme"   # 极端波动


class RiskLevel(str, Enum):
    """风险等级"""

    LOW = "low"  # 低风险
    MEDIUM = "medium"  # 中等风险
    HIGH = "high"  # 高风险
    EXTREME = "extreme"  # 极端风险


class TimeHorizon(str, Enum):
    """时间跨度"""

    SHORT = "short"  # 短期 (几小时-1天)
    MEDIUM = "medium"  # 中期 (几天-1周)
    LONG = "long"  # 长期 (1周以上)


class MarketRegime(BaseModel):
    """
    市场状态判断

    由战略层(Strategist)每小时生成一次,指导战术层(Trader)的交易决策
    """

    model_config = ConfigDict(
        json_encoders={Decimal: str, datetime: lambda v: v.isoformat()}
    )

    # ========== 基础判断 ==========
    bias: MarketBias = Field(..., description="市场偏向")
    confidence: float = Field(..., ge=0, le=1, description="判断信心度 0-1")
    market_structure: MarketStructure = Field(
        ..., description="市场结构: 趋势/震荡/极端波动"
    )

    # ========== 风险评估 ==========
    risk_level: RiskLevel = Field(..., description="当前市场风险等级")

    # ========== 市场叙事 ==========
    market_narrative: str = Field(..., description="市场主线/核心逻辑")
    key_drivers: List[str] = Field(
        default_factory=list, description="关键驱动因素"
    )
    volatility_range: Optional[str] = Field(
        default=None, description="预期波动区间描述，例如 low/medium/high"
    )

    # ========== 策略建议 ==========
    time_horizon: TimeHorizon = Field(..., description="建议持仓周期")
    cash_ratio: float = Field(
        default=0.3, ge=0, le=1, description="建议现金比例 0-1"
    )
    max_exposure: Optional[float] = Field(
        default=None, ge=0, le=1, description="建议的最大总仓占比 (0-1)"
    )

    # ========== 交易建议 ==========
    trading_mode: str = Field(
        default="normal",
        description="交易模式: aggressive(激进)/normal(正常)/conservative(保守)/defensive(防御)",
    )
    position_sizing_multiplier: float = Field(
        default=1.0,
        ge=0,
        le=2.0,
        description="仓位调整系数 (牛市可>1, 熊市<1)",
    )

    # ========== 时间戳 ==========
    timestamp: int = Field(..., description="生成时间戳(毫秒)")
    dt: datetime = Field(..., description="生成时间")
    valid_until: int = Field(..., description="有效期至(毫秒), 通常是生成时间+1小时")

    # ========== 原因说明 ==========
    reasoning: str = Field(..., description="判断理由")

    # ========== 未来扩展字段 (可选) ==========
    macro_indicators: Optional[Dict[str, Any]] = Field(
        None, description="宏观指标 (未来: GDP、利率、通胀等)"
    )
    sentiment_score: Optional[float] = Field(
        None, ge=-1, le=1, description="市场情绪评分 (未来: -1恐慌到1贪婪)"
    )
    news_events: Optional[List[Dict[str, str]]] = Field(
        None, description="重大新闻事件 (未来)"
    )
    correlation_matrix: Optional[Dict[str, Dict[str, float]]] = Field(
        None, description="币种相关性矩阵 (未来优化: 避免持有高度相关的币种)"
    )

    def is_valid(self) -> bool:
        """检查判断是否还在有效期内"""
        now = int(datetime.now().timestamp() * 1000)
        return now < self.valid_until

    def should_be_aggressive(self) -> bool:
        """判断是否应该激进交易"""
        return self.bias == MarketBias.BULLISH and self.confidence > 0.7 and self.risk_level in [
            RiskLevel.LOW,
            RiskLevel.MEDIUM,
        ]

    def should_be_defensive(self) -> bool:
        """判断是否应该防御"""
        return self.bias == MarketBias.BEARISH or self.risk_level == RiskLevel.EXTREME

    def should_reduce_positions(self) -> bool:
        """判断是否应该减仓"""
        return (
            self.bias == MarketBias.BEARISH
            or self.risk_level in [RiskLevel.HIGH, RiskLevel.EXTREME]
        )

    def get_summary(self) -> str:
        """获取简短摘要"""
        parts = [
            f"{self.bias.value.upper()} 市场",
            f"结构: {self.market_structure.value}",
            f"风险: {self.risk_level.value}",
            f"现金比例: {self.cash_ratio:.0%}",
        ]
        if self.volatility_range:
            parts.append(f"波动: {self.volatility_range}")
        if self.max_exposure is not None:
            parts.append(f"仓位上限: {self.max_exposure:.0%}")
        return " | ".join(parts)
