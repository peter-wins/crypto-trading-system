#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
K线数据管理配置

定义多周期K线的采集频率、保留周期等策略
"""

from dataclasses import dataclass
from typing import Dict


@dataclass
class TimeframeConfig:
    """单个时间周期的配置"""
    timeframe: str          # 时间周期 (1m, 5m, 15m, 1h, 4h, 1d)
    collection_interval: int  # 采集间隔（秒）
    retention_days: int     # 数据保留天数（0表示永久）
    limit: int              # 每次采集的K线数量
    priority: int           # 优先级（数字越小优先级越高）
    layer: str              # 所属层级（tactical/strategic）
    incremental_limit: int = 20  # 增量采集时的最大K线数量


# 多周期K线配置
KLINE_CONFIGS: Dict[str, TimeframeConfig] = {
    # 实时层 - 用于短期交易决策
    "1m": TimeframeConfig(
        timeframe="1m",
        collection_interval=30,   # 每30秒采集一次
        retention_days=3,          # 保留3天
        limit=100,                 # 采集100根（约1.6小时）
        priority=1,
        layer="tactical"
    ),
    "5m": TimeframeConfig(
        timeframe="5m",
        collection_interval=60,    # 每60秒采集一次
        retention_days=7,          # 保留7天
        limit=100,                 # 采集100根（约8小时）
        priority=2,
        layer="tactical"
    ),

    # 战术层 - 用于趋势判断
    "15m": TimeframeConfig(
        timeframe="15m",
        collection_interval=300,   # 每5分钟采集一次
        retention_days=30,         # 保留30天
        limit=200,                 # 采集200根（约50小时）
        priority=3,
        layer="tactical"
    ),
    "1h": TimeframeConfig(
        timeframe="1h",
        collection_interval=900,   # 每15分钟采集一次
        retention_days=90,         # 保留90天
        limit=200,                 # 采集200根（约8天）
        priority=4,
        layer="tactical"
    ),

    # 战略层 - 用于大趋势分析
    "4h": TimeframeConfig(
        timeframe="4h",
        collection_interval=3600,  # 每1小时采集一次
        retention_days=180,        # 保留180天
        limit=200,                 # 采集200根（约33天）
        priority=5,
        layer="strategic"
    ),
    "1d": TimeframeConfig(
        timeframe="1d",
        collection_interval=14400, # 每4小时采集一次
        retention_days=0,          # 永久保留
        limit=365,                 # 采集365根（1年）
        priority=6,
        layer="strategic"
    ),
}


# 数据获取策略配置
@dataclass
class DataFetchStrategy:
    """数据获取策略"""
    memory_cache_ttl: int = 5       # 内存缓存有效期（秒）
    redis_cache_ttl: int = 60       # Redis缓存有效期（秒）
    db_cache_ttl: int = 300         # 数据库缓存有效期（秒）
    enable_api_fallback: bool = True  # 启用API兜底


# 默认数据获取策略
DEFAULT_FETCH_STRATEGY = DataFetchStrategy()


# API速率限制配置
@dataclass
class RateLimitConfig:
    """API速率限制配置"""
    max_requests_per_minute: int = 50  # 每分钟最大请求数（保守估计）
    weight_limit_per_minute: int = 2400  # Binance weight限制

    # 各个接口的weight
    ticker_weight: int = 1
    klines_weight: int = 1
    trades_weight: int = 1


DEFAULT_RATE_LIMIT = RateLimitConfig()


def get_enabled_timeframes() -> list[str]:
    """获取启用的时间周期列表"""
    return list(KLINE_CONFIGS.keys())


def get_timeframe_config(timeframe: str) -> TimeframeConfig:
    """获取指定时间周期的配置"""
    return KLINE_CONFIGS.get(timeframe)


def get_tactical_timeframes() -> list[str]:
    """获取战术层时间周期"""
    return [tf for tf, cfg in KLINE_CONFIGS.items() if cfg.layer == "tactical"]


def get_strategic_timeframes() -> list[str]:
    """获取战略层时间周期"""
    return [tf for tf, cfg in KLINE_CONFIGS.items() if cfg.layer == "strategic"]


def estimate_api_usage() -> dict:
    """估算API使用率"""
    total_calls_per_minute = 0
    details = {}

    for tf, cfg in KLINE_CONFIGS.items():
        # 计算每分钟的采集次数
        calls_per_minute = 60 / cfg.collection_interval
        total_calls_per_minute += calls_per_minute

        details[tf] = {
            "interval": cfg.collection_interval,
            "calls_per_minute": round(calls_per_minute, 2),
        }

    # 假设2个交易对
    num_symbols = 2
    total_calls = total_calls_per_minute * num_symbols

    return {
        "total_calls_per_minute": round(total_calls, 2),
        "rate_limit": DEFAULT_RATE_LIMIT.max_requests_per_minute,
        "usage_percentage": round(total_calls / DEFAULT_RATE_LIMIT.max_requests_per_minute * 100, 1),
        "details": details,
        "safe": total_calls < DEFAULT_RATE_LIMIT.max_requests_per_minute * 0.8  # 80%以下安全
    }
