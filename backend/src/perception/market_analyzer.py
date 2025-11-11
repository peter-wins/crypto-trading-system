"""
市场分析器

从K线数据计算技术指标，并生成简洁的市场摘要供LLM使用
"""

from __future__ import annotations

from typing import Dict, Any, List, Optional
from decimal import Decimal
from dataclasses import dataclass
import logging

from src.perception.indicators import PandasIndicatorCalculator


@dataclass
class MarketSummary:
    """市场摘要（用于LLM输入，节省token）"""

    # 基本信息
    symbol: str
    timeframe: str
    current_price: Decimal
    price_change_pct: Decimal  # 价格变化百分比

    # 趋势
    trend: str  # "上升" / "下降" / "震荡"
    trend_strength: str  # "强" / "中" / "弱"

    # 移动平均
    ma20: Decimal
    ma50: Decimal
    price_vs_ma20: str  # "上方" / "下方" / "接近"
    price_vs_ma50: str

    # RSI
    rsi: Decimal
    rsi_signal: str  # "超买" / "超卖" / "中性"

    # MACD
    macd_signal: str  # "金叉" / "死叉" / "中性"
    macd_histogram: Decimal

    # 布林带
    bb_position: str  # "上轨" / "中轨" / "下轨" / "上轨外" / "下轨外"
    bb_squeeze: bool  # 是否收窄（低波动）

    # 波动性
    atr: Decimal
    volatility: str  # "高" / "中" / "低"

    # 成交量
    volume_trend: str  # "放量" / "缩量" / "正常"

    # 关键价位（可选字段必须放在最后）
    support: Optional[Decimal] = None
    resistance: Optional[Decimal] = None

    def to_prompt(self) -> str:
        """
        转换为简洁的文本格式（给LLM用）

        Returns:
            简洁的市场状态描述（约200-300字符）
        """
        prompt = f"""
【{self.symbol} - {self.timeframe}】
价格: {self.current_price} ({self.price_change_pct:+.2f}%)
趋势: {self.trend}趋势（{self.trend_strength}）
均线: MA20={self.ma20}({self.price_vs_ma20}), MA50={self.ma50}({self.price_vs_ma50})
RSI: {self.rsi:.1f} ({self.rsi_signal})
MACD: {self.macd_signal} (柱状图={self.macd_histogram:.2f})
布林带: {self.bb_position}{"，收窄" if self.bb_squeeze else ""}
波动: {self.volatility} (ATR={self.atr:.2f})
成交量: {self.volume_trend}
""".strip()

        if self.support or self.resistance:
            prompt += f"\n关键位: "
            if self.support:
                prompt += f"支撑={self.support} "
            if self.resistance:
                prompt += f"阻力={self.resistance}"

        return prompt


class MarketAnalyzer:
    """市场分析器 - 从K线计算指标并生成摘要"""

    def __init__(self, indicator_calculator: Optional[PandasIndicatorCalculator] = None):
        """
        初始化市场分析器

        Args:
            indicator_calculator: 指标计算器实例
        """
        self.indicator_calculator = indicator_calculator or PandasIndicatorCalculator()
        self.logger = logging.getLogger(__name__)

    def analyze(
        self,
        symbol: str,
        timeframe: str,
        klines: List[Any]
    ) -> MarketSummary:
        """
        分析K线数据并生成市场摘要

        Args:
            symbol: 交易对
            timeframe: 时间周期
            klines: K线数据列表（OHLCV对象）

        Returns:
            MarketSummary对象
        """
        if not klines or len(klines) < 50:
            raise ValueError(f"需要至少50根K线数据，当前只有{len(klines)}根")

        # 提取OHLCV数据
        highs = [k.high for k in klines]
        lows = [k.low for k in klines]
        closes = [k.close for k in klines]
        volumes = [k.volume for k in klines]

        # 当前价格和变化
        current_price = closes[-1]
        price_change_pct = ((closes[-1] - closes[-2]) / closes[-2]) * 100 if len(closes) > 1 else Decimal(0)

        # 计算指标
        ma20 = self.indicator_calculator.calculate_sma(closes, 20)[-1]
        ma50 = self.indicator_calculator.calculate_sma(closes, 50)[-1]
        rsi_values = self.indicator_calculator.calculate_rsi(closes, 14)
        rsi = rsi_values[-1]

        macd_data = self.indicator_calculator.calculate_macd(closes)
        macd_histogram = macd_data["histogram"][-1]
        macd_prev_histogram = macd_data["histogram"][-2] if len(macd_data["histogram"]) > 1 else Decimal(0)

        bb_data = self.indicator_calculator.calculate_bollinger_bands(closes)
        bb_upper = bb_data["upper"][-1]
        bb_middle = bb_data["middle"][-1]
        bb_lower = bb_data["lower"][-1]
        bb_width = bb_upper - bb_lower

        atr_values = self.indicator_calculator.calculate_atr(highs, lows, closes, 14)
        atr = atr_values[-1]

        # 分析趋势
        trend, trend_strength = self._analyze_trend(closes, ma20, ma50)

        # 价格与均线关系
        price_vs_ma20 = self._compare_price_to_ma(current_price, ma20)
        price_vs_ma50 = self._compare_price_to_ma(current_price, ma50)

        # RSI信号
        rsi_signal = self._analyze_rsi(rsi)

        # MACD信号
        macd_signal = self._analyze_macd(macd_histogram, macd_prev_histogram)

        # 布林带位置
        bb_position = self._analyze_bb_position(current_price, bb_upper, bb_middle, bb_lower)
        bb_squeeze = bb_width < (bb_middle * Decimal("0.05"))  # 宽度小于中轨5%视为收窄

        # 波动性
        volatility = self._analyze_volatility(atr, current_price)

        # 成交量趋势
        volume_trend = self._analyze_volume_trend(volumes)

        # 注: 移除了支撑/阻力位计算
        # 原因: 简单的min/max不够准确,且增加token消耗
        # LLM可以从趋势、MA等指标推断关键价位

        return MarketSummary(
            symbol=symbol,
            timeframe=timeframe,
            current_price=current_price,
            price_change_pct=price_change_pct,
            trend=trend,
            trend_strength=trend_strength,
            ma20=ma20,
            ma50=ma50,
            price_vs_ma20=price_vs_ma20,
            price_vs_ma50=price_vs_ma50,
            rsi=rsi,
            rsi_signal=rsi_signal,
            macd_signal=macd_signal,
            macd_histogram=macd_histogram,
            bb_position=bb_position,
            bb_squeeze=bb_squeeze,
            atr=atr,
            volatility=volatility,
            volume_trend=volume_trend,
            support=None,  # 移除了不准确的支撑位计算
            resistance=None  # 移除了不准确的阻力位计算
        )

    def _analyze_trend(
        self,
        closes: List[Decimal],
        ma20: Decimal,
        ma50: Decimal
    ) -> tuple[str, str]:
        """分析趋势方向和强度"""
        current_price = closes[-1]

        # 均线排列判断趋势
        if current_price > ma20 > ma50:
            trend = "上升"
            # 看价格离MA20的距离判断强度
            distance_pct = ((current_price - ma20) / ma20) * 100
            if distance_pct > 3:
                strength = "强"
            elif distance_pct > 1:
                strength = "中"
            else:
                strength = "弱"
        elif current_price < ma20 < ma50:
            trend = "下降"
            distance_pct = ((ma20 - current_price) / ma20) * 100
            if distance_pct > 3:
                strength = "强"
            elif distance_pct > 1:
                strength = "中"
            else:
                strength = "弱"
        else:
            trend = "震荡"
            strength = "中"

        return trend, strength

    def _compare_price_to_ma(self, price: Decimal, ma: Decimal) -> str:
        """比较价格与均线位置"""
        diff_pct = abs((price - ma) / ma * 100)

        if price > ma:
            return "上方" if diff_pct > 0.5 else "接近"
        else:
            return "下方" if diff_pct > 0.5 else "接近"

    def _analyze_rsi(self, rsi: Decimal) -> str:
        """分析RSI信号"""
        if rsi > 70:
            return "超买"
        elif rsi < 30:
            return "超卖"
        else:
            return "中性"

    def _analyze_macd(self, histogram: Decimal, prev_histogram: Decimal) -> str:
        """分析MACD信号"""
        if histogram > 0 and prev_histogram <= 0:
            return "金叉"
        elif histogram < 0 and prev_histogram >= 0:
            return "死叉"
        elif histogram > 0:
            return "多头"
        elif histogram < 0:
            return "空头"
        else:
            return "中性"

    def _analyze_bb_position(
        self,
        price: Decimal,
        upper: Decimal,
        middle: Decimal,
        lower: Decimal
    ) -> str:
        """分析价格在布林带中的位置"""
        if price > upper:
            return "上轨外"
        elif price < lower:
            return "下轨外"
        else:
            # 在上下轨之间，看更接近哪个
            to_upper = abs(price - upper)
            to_middle = abs(price - middle)
            to_lower = abs(price - lower)

            min_dist = min(to_upper, to_middle, to_lower)
            if min_dist == to_upper:
                return "上轨"
            elif min_dist == to_lower:
                return "下轨"
            else:
                return "中轨"

    def _analyze_volatility(self, atr: Decimal, price: Decimal) -> str:
        """分析波动性"""
        atr_pct = (atr / price) * 100

        if atr_pct > 3:
            return "高"
        elif atr_pct > 1:
            return "中"
        else:
            return "低"

    def _analyze_volume_trend(self, volumes: List[Decimal]) -> str:
        """分析成交量趋势"""
        if len(volumes) < 20:
            return "正常"

        recent_avg = sum(volumes[-10:]) / 10
        previous_avg = sum(volumes[-20:-10]) / 10

        change_pct = ((recent_avg - previous_avg) / previous_avg) * 100

        if change_pct > 20:
            return "放量"
        elif change_pct < -20:
            return "缩量"
        else:
            return "正常"
