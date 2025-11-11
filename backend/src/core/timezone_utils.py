"""
时区工具模块

提供统一的时区转换和时间格式化功能
"""

from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from src.core.config import get_config


class TimezoneHelper:
    """时区帮助类"""

    _instance: Optional["TimezoneHelper"] = None
    _local_tz: ZoneInfo

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            config = get_config()
            cls._instance._local_tz = ZoneInfo(config.timezone)
        return cls._instance

    @property
    def local_tz(self) -> ZoneInfo:
        """获取配置的本地时区"""
        return self._local_tz

    def now_local(self) -> datetime:
        """
        获取当前本地时间（带时区信息）

        Returns:
            本地时区的当前时间
        """
        return datetime.now(self._local_tz)

    def now_utc(self) -> datetime:
        """
        获取当前UTC时间（带时区信息）

        Returns:
            UTC时区的当前时间
        """
        return datetime.now(timezone.utc)

    def to_local(self, dt: datetime) -> datetime:
        """
        将任意时区的datetime转换为本地时区

        Args:
            dt: 带时区信息的datetime对象

        Returns:
            本地时区的datetime对象
        """
        if dt.tzinfo is None:
            # 如果没有时区信息，假设为UTC
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(self._local_tz)

    def to_utc(self, dt: datetime) -> datetime:
        """
        将任意时区的datetime转换为UTC

        Args:
            dt: 带时区信息的datetime对象

        Returns:
            UTC时区的datetime对象
        """
        if dt.tzinfo is None:
            # 如果没有时区信息，假设为本地时区
            dt = dt.replace(tzinfo=self._local_tz)
        return dt.astimezone(timezone.utc)

    def format_local(
        self,
        dt: datetime,
        fmt: str = "%Y-%m-%d %H:%M:%S %Z"
    ) -> str:
        """
        将datetime格式化为本地时区字符串

        Args:
            dt: 带时区信息的datetime对象
            fmt: 格式化字符串

        Returns:
            格式化后的本地时间字符串
        """
        local_dt = self.to_local(dt)
        return local_dt.strftime(fmt)

    def format_utc(
        self,
        dt: datetime,
        fmt: str = "%Y-%m-%d %H:%M:%S %Z"
    ) -> str:
        """
        将datetime格式化为UTC时区字符串

        Args:
            dt: 带时区信息的datetime对象
            fmt: 格式化字符串

        Returns:
            格式化后的UTC时间字符串
        """
        utc_dt = self.to_utc(dt)
        return utc_dt.strftime(fmt)

    def format_dual(
        self,
        dt: datetime,
        fmt: str = "%Y-%m-%d %H:%M:%S"
    ) -> str:
        """
        格式化为双时区显示（本地 + UTC）

        Args:
            dt: 带时区信息的datetime对象
            fmt: 格式化字符串（不包含时区标识）

        Returns:
            "本地时间 (UTC时间)" 格式的字符串
        """
        local_dt = self.to_local(dt)
        utc_dt = self.to_utc(dt)

        local_str = local_dt.strftime(fmt)
        utc_str = utc_dt.strftime(fmt)

        # 获取时区缩写
        local_tz_name = local_dt.strftime("%Z")
        utc_tz_name = "UTC"

        return f"{local_str} {local_tz_name} (UTC: {utc_str})"

    def parse_local(self, time_str: str, fmt: str = "%Y-%m-%d %H:%M:%S") -> datetime:
        """
        解析本地时区的时间字符串

        Args:
            time_str: 时间字符串
            fmt: 解析格式

        Returns:
            本地时区的datetime对象
        """
        dt = datetime.strptime(time_str, fmt)
        return dt.replace(tzinfo=self._local_tz)

    def get_timezone_name(self) -> str:
        """获取时区名称"""
        return str(self._local_tz)


# 全局实例
_tz_helper: Optional[TimezoneHelper] = None


def get_timezone_helper() -> TimezoneHelper:
    """
    获取时区帮助类的全局实例（单例）

    Returns:
        TimezoneHelper对象
    """
    global _tz_helper
    if _tz_helper is None:
        _tz_helper = TimezoneHelper()
    return _tz_helper


# 便捷函数
def now_local() -> datetime:
    """获取当前本地时间"""
    return get_timezone_helper().now_local()


def now_utc() -> datetime:
    """获取当前UTC时间"""
    return get_timezone_helper().now_utc()


def to_local(dt: datetime) -> datetime:
    """转换为本地时区"""
    return get_timezone_helper().to_local(dt)


def to_utc(dt: datetime) -> datetime:
    """转换为UTC时区"""
    return get_timezone_helper().to_utc(dt)


def format_local(dt: datetime, fmt: str = "%Y-%m-%d %H:%M:%S %Z") -> str:
    """格式化为本地时间字符串"""
    return get_timezone_helper().format_local(dt, fmt)


def format_utc(dt: datetime, fmt: str = "%Y-%m-%d %H:%M:%S %Z") -> str:
    """格式化为UTC时间字符串"""
    return get_timezone_helper().format_utc(dt, fmt)


def format_dual(dt: datetime, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """格式化为双时区显示"""
    return get_timezone_helper().format_dual(dt, fmt)


if __name__ == "__main__":
    # 测试代码
    print("=== 时区工具测试 ===\n")

    tz = get_timezone_helper()
    print(f"配置的时区: {tz.get_timezone_name()}\n")

    # 当前时间
    local_now = now_local()
    utc_now = now_utc()

    print(f"当前本地时间: {format_local(local_now)}")
    print(f"当前UTC时间: {format_utc(utc_now)}")
    print(f"双时区显示: {format_dual(local_now)}\n")

    # 时区转换
    print("=== 时区转换测试 ===")
    test_utc = datetime(2025, 11, 8, 18, 19, 49, tzinfo=timezone.utc)
    print(f"UTC时间: {format_utc(test_utc)}")
    print(f"转换为本地: {format_local(test_utc)}")
    print(f"双时区显示: {format_dual(test_utc)}")
