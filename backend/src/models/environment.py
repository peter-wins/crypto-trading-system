"""
Market Environment Models

定义感知层输出的市场环境数据结构
包含宏观经济、美股、情绪、新闻等外部数据
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class MacroData(BaseModel):
    """宏观经济数据"""

    model_config = ConfigDict(
        json_encoders={Decimal: str, datetime: lambda v: v.isoformat()}
    )

    # 美联储
    fed_rate: Optional[float] = Field(None, description="联邦基金利率 (%)")
    fed_rate_trend: Optional[str] = Field(
        None, description="利率趋势: raising/cutting/holding"
    )

    # 经济指标
    cpi: Optional[float] = Field(None, description="CPI 通胀率 (%)")
    unemployment: Optional[float] = Field(None, description="失业率 (%)")

    # 市场指标
    dxy: Optional[float] = Field(None, description="美元指数")
    dxy_change_24h: Optional[float] = Field(None, description="美元指数24h变化 (%)")
    gold_price: Optional[float] = Field(None, description="黄金价格 (USD/oz)")
    oil_price: Optional[float] = Field(None, description="原油价格 (USD/barrel)")

    # 更新时间
    updated_at: Optional[datetime] = Field(None, description="数据更新时间")


class StockMarketData(BaseModel):
    """美股市场数据"""

    model_config = ConfigDict(
        json_encoders={Decimal: str, datetime: lambda v: v.isoformat()}
    )

    # 指数
    sp500: Optional[float] = Field(None, description="标普500指数")
    sp500_change_24h: Optional[float] = Field(None, description="标普500 24h变化 (%)")
    nasdaq: Optional[float] = Field(None, description="纳斯达克指数")
    nasdaq_change_24h: Optional[float] = Field(
        None, description="纳斯达克 24h变化 (%)"
    )

    # 加密相关股票
    coin_stock: Optional[float] = Field(None, description="COIN (Coinbase) 股价")
    coin_change_24h: Optional[float] = Field(None, description="COIN 24h变化 (%)")
    mstr_stock: Optional[float] = Field(None, description="MSTR (MicroStrategy) 股价")
    mstr_change_24h: Optional[float] = Field(None, description="MSTR 24h变化 (%)")

    # 相关性
    correlation_with_crypto: Optional[float] = Field(
        None, ge=-1, le=1, description="与加密货币的相关性"
    )

    # 更新时间
    updated_at: Optional[datetime] = Field(None, description="数据更新时间")


class SentimentData(BaseModel):
    """市场情绪数据"""

    model_config = ConfigDict(
        json_encoders={Decimal: str, datetime: lambda v: v.isoformat()}
    )

    # 恐慌贪婪指数
    fear_greed_index: Optional[int] = Field(
        None, ge=0, le=100, description="恐慌贪婪指数 (0=极度恐慌, 100=极度贪婪)"
    )
    fear_greed_label: Optional[str] = Field(
        None,
        description="情绪标签: extreme_fear/fear/neutral/greed/extreme_greed",
    )

    # 资金费率 (正数=多头付空头, 负数=空头付多头)
    btc_funding_rate: Optional[float] = Field(None, description="BTC 资金费率 (%)")
    eth_funding_rate: Optional[float] = Field(None, description="ETH 资金费率 (%)")

    # 多空比
    btc_long_short_ratio: Optional[float] = Field(None, description="BTC 多空比")
    eth_long_short_ratio: Optional[float] = Field(None, description="ETH 多空比")

    # 社交媒体 (未来)
    twitter_sentiment: Optional[float] = Field(
        None, ge=-1, le=1, description="Twitter 情绪评分 (-1负面到1正面)"
    )
    reddit_sentiment: Optional[float] = Field(
        None, ge=-1, le=1, description="Reddit 情绪评分"
    )

    # 更新时间
    updated_at: Optional[datetime] = Field(None, description="数据更新时间")

    def get_overall_sentiment(self) -> str:
        """获取综合情绪判断"""
        if self.fear_greed_index is None:
            return "unknown"

        if self.fear_greed_index < 20:
            return "extreme_fear"
        elif self.fear_greed_index < 40:
            return "fear"
        elif self.fear_greed_index < 60:
            return "neutral"
        elif self.fear_greed_index < 80:
            return "greed"
        else:
            return "extreme_greed"


class NewsEvent(BaseModel):
    """新闻事件"""

    model_config = ConfigDict(
        json_encoders={Decimal: str, datetime: lambda v: v.isoformat()}
    )

    timestamp: int = Field(..., description="事件时间戳 (毫秒)")
    dt: datetime = Field(..., description="事件时间")
    title: str = Field(..., description="新闻标题")
    summary: str = Field(..., description="新闻摘要")
    source: str = Field(..., description="新闻来源")

    # LLM 分析结果
    impact_level: str = Field(
        ..., description="影响等级: low/medium/high/critical"
    )
    sentiment: str = Field(..., description="情绪: positive/neutral/negative")
    related_symbols: List[str] = Field(
        default_factory=list, description="相关币种"
    )

    # 原始链接
    url: Optional[str] = Field(None, description="新闻链接")

    def is_high_impact(self) -> bool:
        """是否为高影响新闻"""
        return self.impact_level in ["high", "critical"]


class MarketEnvironment(BaseModel):
    """
    市场环境数据汇总

    由感知层每小时生成,供战略层分析使用
    汇总了宏观、美股、情绪、新闻等所有外部数据
    """

    model_config = ConfigDict(
        json_encoders={Decimal: str, datetime: lambda v: v.isoformat()}
    )

    timestamp: int = Field(..., description="生成时间戳 (毫秒)")
    dt: datetime = Field(..., description="生成时间")

    # ========== 外部数据 ==========
    macro: Optional[MacroData] = Field(None, description="宏观经济数据")
    stock_market: Optional[StockMarketData] = Field(None, description="美股市场数据")
    sentiment: Optional[SentimentData] = Field(None, description="市场情绪数据")

    # 新闻事件 (最近24小时的重大新闻)
    recent_news: List[NewsEvent] = Field(
        default_factory=list, description="最近24小时的重大新闻"
    )

    # ========== 加密市场概览 ==========
    crypto_market_cap: Optional[Decimal] = Field(
        None, description="加密货币总市值 (USD)"
    )
    crypto_market_cap_change_24h: Optional[float] = Field(
        None, description="总市值24h变化 (%)"
    )
    btc_dominance: Optional[float] = Field(
        None, ge=0, le=100, description="BTC 市值占比 (%)"
    )
    total_volume_24h: Optional[Decimal] = Field(
        None, description="24h 总交易量 (USD)"
    )

    # ========== 数据质量指标 ==========
    data_completeness: float = Field(
        default=0.0,
        ge=0,
        le=1,
        description="数据完整度 (0-1, 1表示所有数据都成功采集)",
    )

    def get_summary(self) -> str:
        """获取环境摘要"""
        parts = []

        if self.macro and self.macro.fed_rate is not None:
            parts.append(f"利率:{self.macro.fed_rate}%")

        if self.macro and self.macro.dxy_change_24h is not None:
            parts.append(f"DXY:{self.macro.dxy_change_24h:+.2f}%")

        if self.stock_market and self.stock_market.sp500_change_24h is not None:
            parts.append(f"标普:{self.stock_market.sp500_change_24h:+.2f}%")

        if self.sentiment and self.sentiment.fear_greed_index is not None:
            parts.append(f"情绪:{self.sentiment.get_overall_sentiment()}")

        high_impact_news = [n for n in self.recent_news if n.is_high_impact()]
        if high_impact_news:
            parts.append(f"{len(high_impact_news)}条重大新闻")

        if self.crypto_market_cap_change_24h is not None:
            parts.append(f"加密:{self.crypto_market_cap_change_24h:+.2f}%")

        return " | ".join(parts) if parts else "数据采集中"

    def calculate_data_completeness(self) -> None:
        """计算数据完整度"""
        total = 0
        completed = 0

        # 检查宏观数据
        total += 1
        if self.macro and self.macro.fed_rate is not None:
            completed += 1

        # 检查美股数据
        total += 1
        if self.stock_market and self.stock_market.sp500 is not None:
            completed += 1

        # 检查情绪数据
        total += 1
        if self.sentiment and self.sentiment.fear_greed_index is not None:
            completed += 1

        # 检查新闻
        total += 1
        if len(self.recent_news) > 0:
            completed += 1

        self.data_completeness = completed / total if total > 0 else 0.0

    def is_ready_for_analysis(self) -> bool:
        """检查数据是否足够用于分析"""
        # 至少要有情绪数据或新闻数据之一
        return self.data_completeness >= 0.5
