"""
技术指标计算模块

本模块实现各种技术指标的计算功能。
"""

from __future__ import annotations

from decimal import Decimal
from typing import List, Dict
import pandas as pd
import pandas_ta as ta

from src.core.logger import get_logger


logger = get_logger(__name__)


class PandasIndicatorCalculator:
    """基于Pandas-TA的技术指标计算器"""

    def __init__(self):
        """初始化指标计算器"""
        self.logger = logger

    def _to_float_list(self, prices: List[Decimal]) -> List[float]:
        """将Decimal列表转换为float列表"""
        return [float(p) for p in prices]

    def _to_decimal_list(self, values: pd.Series) -> List[Decimal]:
        """将pandas Series转换为Decimal列表"""
        return [Decimal(str(v)) if pd.notna(v) else Decimal("0") for v in values]

    def calculate_sma(
        self,
        prices: List[Decimal],
        period: int
    ) -> List[Decimal]:
        """
        计算简单移动平均

        Args:
            prices: 价格列表
            period: 周期

        Returns:
            SMA值列表
        """
        try:
            df = pd.DataFrame({"close": self._to_float_list(prices)})
            sma = ta.sma(df["close"], length=period)
            return self._to_decimal_list(sma)
        except Exception as e:
            self.logger.error(f"Error calculating SMA: {e}")
            return [Decimal("0")] * len(prices)

    def calculate_ema(
        self,
        prices: List[Decimal],
        period: int
    ) -> List[Decimal]:
        """
        计算指数移动平均

        Args:
            prices: 价格列表
            period: 周期

        Returns:
            EMA值列表
        """
        try:
            df = pd.DataFrame({"close": self._to_float_list(prices)})
            ema = ta.ema(df["close"], length=period)
            return self._to_decimal_list(ema)
        except Exception as e:
            self.logger.error(f"Error calculating EMA: {e}")
            return [Decimal("0")] * len(prices)

    def calculate_rsi(
        self,
        prices: List[Decimal],
        period: int = 14
    ) -> List[Decimal]:
        """
        计算RSI（相对强弱指数）

        Args:
            prices: 价格列表
            period: 周期，默认14

        Returns:
            RSI值列表（0-100）
        """
        try:
            df = pd.DataFrame({"close": self._to_float_list(prices)})
            rsi = ta.rsi(df["close"], length=period)
            return self._to_decimal_list(rsi)
        except Exception as e:
            self.logger.error(f"Error calculating RSI: {e}")
            return [Decimal("50")] * len(prices)

    def calculate_macd(
        self,
        prices: List[Decimal],
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9
    ) -> Dict[str, List[Decimal]]:
        """
        计算MACD指标

        Args:
            prices: 价格列表
            fast_period: 快线周期
            slow_period: 慢线周期
            signal_period: 信号线周期

        Returns:
            {"macd": [...], "signal": [...], "histogram": [...]}
        """
        try:
            df = pd.DataFrame({"close": self._to_float_list(prices)})
            macd_result = ta.macd(
                df["close"],
                fast=fast_period,
                slow=slow_period,
                signal=signal_period
            )

            return {
                "macd": self._to_decimal_list(macd_result[f"MACD_{fast_period}_{slow_period}_{signal_period}"]),
                "signal": self._to_decimal_list(macd_result[f"MACDs_{fast_period}_{slow_period}_{signal_period}"]),
                "histogram": self._to_decimal_list(macd_result[f"MACDh_{fast_period}_{slow_period}_{signal_period}"])
            }
        except Exception as e:
            self.logger.error(f"Error calculating MACD: {e}")
            zero_list = [Decimal("0")] * len(prices)
            return {
                "macd": zero_list,
                "signal": zero_list,
                "histogram": zero_list
            }

    def calculate_bollinger_bands(
        self,
        prices: List[Decimal],
        period: int = 20,
        std_dev: float = 2.0
    ) -> Dict[str, List[Decimal]]:
        """
        计算布林带

        Args:
            prices: 价格列表
            period: 周期
            std_dev: 标准差倍数

        Returns:
            {"upper": [...], "middle": [...], "lower": [...]}
        """
        try:
            df = pd.DataFrame({"close": self._to_float_list(prices)})
            bbands = ta.bbands(df["close"], length=period, std=std_dev)

            if bbands is None or bbands.empty:
                self.logger.warning("Bollinger Bands calculation returned None or empty DataFrame")
                zero_list = [Decimal("0")] * len(prices)
                return {"upper": zero_list, "middle": zero_list, "lower": zero_list}

            # pandas-ta 的列名格式为: BBU_{length}_{std}_{mamode}
            # 例如: BBU_20_2.0_2.0, BBM_20_2.0_2.0, BBL_20_2.0_2.0
            col_suffix = f"{period}_{std_dev}_{std_dev}"

            return {
                "upper": self._to_decimal_list(bbands[f"BBU_{col_suffix}"]),
                "middle": self._to_decimal_list(bbands[f"BBM_{col_suffix}"]),
                "lower": self._to_decimal_list(bbands[f"BBL_{col_suffix}"])
            }
        except Exception as e:
            self.logger.error(f"Error calculating Bollinger Bands: {e}")
            zero_list = [Decimal("0")] * len(prices)
            return {
                "upper": zero_list,
                "middle": zero_list,
                "lower": zero_list
            }

    def calculate_atr(
        self,
        high: List[Decimal],
        low: List[Decimal],
        close: List[Decimal],
        period: int = 14
    ) -> List[Decimal]:
        """
        计算ATR（平均真实波幅）

        Args:
            high: 最高价列表
            low: 最低价列表
            close: 收盘价列表
            period: 周期

        Returns:
            ATR值列表
        """
        try:
            df = pd.DataFrame({
                "high": self._to_float_list(high),
                "low": self._to_float_list(low),
                "close": self._to_float_list(close)
            })
            atr = ta.atr(df["high"], df["low"], df["close"], length=period)
            return self._to_decimal_list(atr)
        except Exception as e:
            self.logger.error(f"Error calculating ATR: {e}")
            return [Decimal("0")] * len(close)

    def calculate_adx(
        self,
        high: List[Decimal],
        low: List[Decimal],
        close: List[Decimal],
        period: int = 14
    ) -> Dict[str, List[Decimal]]:
        """
        计算ADX（平均趋向指数）

        Args:
            high: 最高价列表
            low: 最低价列表
            close: 收盘价列表
            period: 周期

        Returns:
            {"adx": [...], "dmp": [...], "dmn": [...]}
        """
        try:
            df = pd.DataFrame({
                "high": self._to_float_list(high),
                "low": self._to_float_list(low),
                "close": self._to_float_list(close)
            })
            adx_result = ta.adx(df["high"], df["low"], df["close"], length=period)

            return {
                "adx": self._to_decimal_list(adx_result[f"ADX_{period}"]),
                "dmp": self._to_decimal_list(adx_result[f"DMP_{period}"]),
                "dmn": self._to_decimal_list(adx_result[f"DMN_{period}"])
            }
        except Exception as e:
            self.logger.error(f"Error calculating ADX: {e}")
            zero_list = [Decimal("0")] * len(close)
            return {
                "adx": zero_list,
                "dmp": zero_list,
                "dmn": zero_list
            }

    def calculate_stochastic(
        self,
        high: List[Decimal],
        low: List[Decimal],
        close: List[Decimal],
        k_period: int = 14,
        d_period: int = 3
    ) -> Dict[str, List[Decimal]]:
        """
        计算随机指标

        Args:
            high: 最高价列表
            low: 最低价列表
            close: 收盘价列表
            k_period: K线周期
            d_period: D线周期

        Returns:
            {"k": [...], "d": [...]}
        """
        try:
            df = pd.DataFrame({
                "high": self._to_float_list(high),
                "low": self._to_float_list(low),
                "close": self._to_float_list(close)
            })
            stoch = ta.stoch(df["high"], df["low"], df["close"], k=k_period, d=d_period)

            return {
                "k": self._to_decimal_list(stoch[f"STOCHk_{k_period}_{d_period}_3"]),
                "d": self._to_decimal_list(stoch[f"STOCHd_{k_period}_{d_period}_3"])
            }
        except Exception as e:
            self.logger.error(f"Error calculating Stochastic: {e}")
            zero_list = [Decimal("50")] * len(close)
            return {
                "k": zero_list,
                "d": zero_list
            }

    def calculate_obv(
        self,
        close: List[Decimal],
        volume: List[Decimal]
    ) -> List[Decimal]:
        """
        计算OBV（能量潮）

        Args:
            close: 收盘价列表
            volume: 成交量列表

        Returns:
            OBV值列表
        """
        try:
            df = pd.DataFrame({
                "close": self._to_float_list(close),
                "volume": self._to_float_list(volume)
            })
            obv = ta.obv(df["close"], df["volume"])
            return self._to_decimal_list(obv)
        except Exception as e:
            self.logger.error(f"Error calculating OBV: {e}")
            return [Decimal("0")] * len(close)

    def calculate_all_indicators(
        self,
        high: List[Decimal],
        low: List[Decimal],
        close: List[Decimal],
        volume: List[Decimal]
    ) -> Dict[str, any]:
        """
        计算所有常用指标

        Args:
            high: 最高价列表
            low: 最低价列表
            close: 收盘价列表
            volume: 成交量列表

        Returns:
            包含所有指标的字典
        """
        return {
            "sma_20": self.calculate_sma(close, 20),
            "sma_50": self.calculate_sma(close, 50),
            "ema_12": self.calculate_ema(close, 12),
            "ema_26": self.calculate_ema(close, 26),
            "rsi_14": self.calculate_rsi(close, 14),
            "macd": self.calculate_macd(close),
            "bollinger": self.calculate_bollinger_bands(close),
            "atr_14": self.calculate_atr(high, low, close, 14),
            "adx": self.calculate_adx(high, low, close, 14),
            "stochastic": self.calculate_stochastic(high, low, close),
            "obv": self.calculate_obv(close, volume)
        }
