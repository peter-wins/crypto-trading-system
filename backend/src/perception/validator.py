"""
数据验证和标准化模块

本模块实现数据完整性检查、异常值检测和数据标准化功能。
"""

from __future__ import annotations

from decimal import Decimal
from typing import List, Optional, Tuple
import pandas as pd
import numpy as np

from src.core.logger import get_logger
from src.models.market import OHLCVData


logger = get_logger(__name__)


class MarketDataValidator:
    """市场数据验证器"""

    def __init__(
        self,
        max_price_change_pct: float = 50.0,
        max_volume_change_multiplier: float = 10.0
    ):
        """
        初始化验证器

        Args:
            max_price_change_pct: 最大价格变化百分比（用于异常检测）
            max_volume_change_multiplier: 最大成交量变化倍数
        """
        self.max_price_change_pct = max_price_change_pct
        self.max_volume_change_multiplier = max_volume_change_multiplier
        self.logger = logger

    def validate_ohlcv(self, data: OHLCVData) -> Tuple[bool, Optional[str]]:
        """
        验证单条OHLCV数据的完整性

        Args:
            data: OHLCV数据对象

        Returns:
            (是否有效, 错误信息)
        """
        # 检查价格为正
        if data.open <= 0 or data.high <= 0 or data.low <= 0 or data.close <= 0:
            return False, "Price must be positive"

        # 检查high >= low
        if data.high < data.low:
            return False, "High price must be >= low price"

        # 检查open, close在high和low之间
        if not (data.low <= data.open <= data.high):
            return False, "Open price must be between low and high"

        if not (data.low <= data.close <= data.high):
            return False, "Close price must be between low and high"

        # 检查成交量非负
        if data.volume < 0:
            return False, "Volume cannot be negative"

        # 检查时间戳有效
        if data.timestamp <= 0:
            return False, "Invalid timestamp"

        return True, None

    def validate_ohlcv_list(
        self,
        data_list: List[OHLCVData]
    ) -> Tuple[bool, List[str]]:
        """
        验证OHLCV数据列表

        Args:
            data_list: OHLCV数据列表

        Returns:
            (是否全部有效, 错误信息列表)
        """
        errors = []

        for i, data in enumerate(data_list):
            is_valid, error = self.validate_ohlcv(data)
            if not is_valid:
                errors.append(f"Index {i}: {error}")

        return len(errors) == 0, errors

    def detect_price_anomalies(
        self,
        data_list: List[OHLCVData]
    ) -> List[int]:
        """
        检测价格异常值

        Args:
            data_list: OHLCV数据列表

        Returns:
            异常数据的索引列表
        """
        if len(data_list) < 2:
            return []

        anomalies = []

        for i in range(1, len(data_list)):
            prev_close = float(data_list[i - 1].close)
            curr_close = float(data_list[i].close)

            # 计算价格变化百分比
            if prev_close > 0:
                change_pct = abs((curr_close - prev_close) / prev_close * 100)

                if change_pct > self.max_price_change_pct:
                    anomalies.append(i)
                    self.logger.warning(
                        f"Price anomaly detected at index {i}: "
                        f"change {change_pct:.2f}%"
                    )

        return anomalies

    def detect_volume_anomalies(
        self,
        data_list: List[OHLCVData]
    ) -> List[int]:
        """
        检测成交量异常值

        Args:
            data_list: OHLCV数据列表

        Returns:
            异常数据的索引列表
        """
        if len(data_list) < 5:
            return []

        anomalies = []
        volumes = [float(d.volume) for d in data_list]

        # 计算移动平均
        window_size = 5
        for i in range(window_size, len(volumes)):
            avg_volume = np.mean(volumes[i - window_size:i])

            if avg_volume > 0:
                ratio = volumes[i] / avg_volume

                if ratio > self.max_volume_change_multiplier:
                    anomalies.append(i)
                    self.logger.warning(
                        f"Volume anomaly detected at index {i}: "
                        f"ratio {ratio:.2f}x"
                    )

        return anomalies

    def fill_missing_data(
        self,
        data_list: List[OHLCVData],
        method: str = "forward"
    ) -> List[OHLCVData]:
        """
        填充缺失数据

        Args:
            data_list: OHLCV数据列表
            method: 填充方法 ("forward", "backward", "interpolate")

        Returns:
            填充后的数据列表
        """
        if not data_list:
            return []

        # 转换为DataFrame
        df = pd.DataFrame([
            {
                "timestamp": d.timestamp,
                "open": float(d.open),
                "high": float(d.high),
                "low": float(d.low),
                "close": float(d.close),
                "volume": float(d.volume),
                "symbol": d.symbol,
                "dt": d.dt
            }
            for d in data_list
        ])

        # 填充缺失值
        if method == "forward":
            df = df.ffill()
        elif method == "backward":
            df = df.bfill()
        elif method == "interpolate":
            numeric_cols = ["open", "high", "low", "close", "volume"]
            df[numeric_cols] = df[numeric_cols].interpolate(method="linear")
        else:
            raise ValueError(f"Unknown fill method: {method}")

        # 转换回OHLCVData列表
        result = []
        for _, row in df.iterrows():
            result.append(OHLCVData(
                symbol=row["symbol"],
                timestamp=int(row["timestamp"]),
                dt=row["dt"],
                open=Decimal(str(row["open"])),
                high=Decimal(str(row["high"])),
                low=Decimal(str(row["low"])),
                close=Decimal(str(row["close"])),
                volume=Decimal(str(row["volume"]))
            ))

        return result

    def remove_outliers(
        self,
        data_list: List[OHLCVData],
        column: str = "close",
        z_threshold: float = 3.0
    ) -> List[OHLCVData]:
        """
        移除异常值（使用Z-score方法）

        Args:
            data_list: OHLCV数据列表
            column: 要检查的列 ("open", "high", "low", "close", "volume")
            z_threshold: Z-score阈值

        Returns:
            移除异常值后的数据列表
        """
        if len(data_list) < 10:
            return data_list

        # 提取指定列的值
        values = [float(getattr(d, column)) for d in data_list]

        # 计算Z-score
        mean = np.mean(values)
        std = np.std(values)

        if std == 0:
            return data_list

        z_scores = [(v - mean) / std for v in values]

        # 过滤异常值
        result = []
        removed_count = 0

        for i, (data, z_score) in enumerate(zip(data_list, z_scores)):
            if abs(z_score) <= z_threshold:
                result.append(data)
            else:
                removed_count += 1
                self.logger.debug(
                    f"Removed outlier at index {i}: "
                    f"{column}={getattr(data, column)}, z-score={z_score:.2f}"
                )

        if removed_count > 0:
            self.logger.info(
                f"Removed {removed_count} outliers from {len(data_list)} records"
            )

        return result

    def resample_data(
        self,
        data_list: List[OHLCVData],
        target_timeframe: str
    ) -> List[OHLCVData]:
        """
        重采样数据到目标时间框架

        Args:
            data_list: OHLCV数据列表
            target_timeframe: 目标时间框架 ("5m", "15m", "1h", "4h", "1d")

        Returns:
            重采样后的数据列表
        """
        if not data_list:
            return []

        # 转换为DataFrame
        df = pd.DataFrame([
            {
                "timestamp": d.dt,
                "open": float(d.open),
                "high": float(d.high),
                "low": float(d.low),
                "close": float(d.close),
                "volume": float(d.volume),
                "symbol": d.symbol
            }
            for d in data_list
        ])

        df.set_index("timestamp", inplace=True)

        # 转换时间框架格式
        tf_map = {
            "1m": "1min", "5m": "5min", "15m": "15min", "30m": "30min",
            "1h": "1H", "4h": "4H", "1d": "1D"
        }
        resample_rule = tf_map.get(target_timeframe, target_timeframe)

        # 重采样
        resampled = df.resample(resample_rule).agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
            "symbol": "first"
        })

        resampled = resampled.dropna()

        # 转换回OHLCVData列表
        result = []
        for timestamp, row in resampled.iterrows():
            result.append(OHLCVData(
                symbol=row["symbol"],
                timestamp=int(timestamp.timestamp() * 1000),
                dt=timestamp,
                open=Decimal(str(row["open"])),
                high=Decimal(str(row["high"])),
                low=Decimal(str(row["low"])),
                close=Decimal(str(row["close"])),
                volume=Decimal(str(row["volume"]))
            ))

        return result

    def get_data_quality_report(
        self,
        data_list: List[OHLCVData]
    ) -> dict:
        """
        生成数据质量报告

        Args:
            data_list: OHLCV数据列表

        Returns:
            数据质量报告字典
        """
        if not data_list:
            return {"error": "No data provided"}

        is_valid, errors = self.validate_ohlcv_list(data_list)
        price_anomalies = self.detect_price_anomalies(data_list)
        volume_anomalies = self.detect_volume_anomalies(data_list)

        return {
            "total_records": len(data_list),
            "is_valid": is_valid,
            "validation_errors": errors,
            "price_anomaly_count": len(price_anomalies),
            "price_anomaly_indices": price_anomalies,
            "volume_anomaly_count": len(volume_anomalies),
            "volume_anomaly_indices": volume_anomalies,
            "data_quality_score": self._calculate_quality_score(
                len(data_list),
                len(errors),
                len(price_anomalies),
                len(volume_anomalies)
            )
        }

    def _calculate_quality_score(
        self,
        total: int,
        errors: int,
        price_anomalies: int,
        volume_anomalies: int
    ) -> float:
        """计算数据质量分数（0-100）"""
        if total == 0:
            return 0.0

        error_penalty = (errors / total) * 50
        price_anomaly_penalty = (price_anomalies / total) * 25
        volume_anomaly_penalty = (volume_anomalies / total) * 25

        score = 100.0 - error_penalty - price_anomaly_penalty - volume_anomaly_penalty
        return max(0.0, min(100.0, score))
