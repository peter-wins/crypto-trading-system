#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Market Data Collection Service

后台市场数据采集服务,负责定期采集市场数据并更新到缓存。
将数据采集逻辑从主系统中分离,提高代码的可维护性和可测试性。
"""

import asyncio
import logging
from decimal import Decimal
from statistics import pstdev
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timezone

from src.services.market_data.ccxt_collector import CCXTMarketDataCollector
from src.perception.indicators import PandasIndicatorCalculator
from src.memory.short_term import RedisShortTermMemory
from src.models.memory import MarketContext
from src.core.exceptions import TradingSystemError


class MarketDataCollector:
    """
    后台市场数据采集服务

    职责:
    1. 定期采集市场行情数据
    2. 计算技术指标
    3. 更新短期内存(Redis)
    4. 维护最新的市场快照
    """

    def __init__(
        self,
        symbols: List[str],
        market_collector: CCXTMarketDataCollector,
        indicator_calculator: PandasIndicatorCalculator,
        short_term_memory: RedisShortTermMemory,
        collection_interval: int = 3,
        logger: Optional[logging.Logger] = None,
        dao: Optional[Any] = None,
        save_klines: bool = True,
    ):
        """
        初始化数据采集服务

        Args:
            symbols: 要采集的交易对列表
            market_collector: 市场数据采集器
            indicator_calculator: 技术指标计算器
            short_term_memory: 短期内存存储
            collection_interval: 采集间隔(秒),默认3秒
            logger: 日志记录器
            dao: 数据库DAO对象（可选，用于保存K线数据）
            save_klines: 是否保存K线数据到数据库
        """
        self.symbols = symbols
        self.market_collector = market_collector
        self.indicator_calculator = indicator_calculator
        self.short_term_memory = short_term_memory
        self.collection_interval = collection_interval
        self.logger = logger or logging.getLogger(__name__)
        self.dao = dao
        self.save_klines = save_klines

        # 运行状态
        self.running = False
        self._task: Optional[asyncio.Task] = None

        # 最新的市场快照缓存
        self._last_snapshots: Dict[str, Dict[str, Any]] = {}
        self.primary_timeframe = "1h"
        self.cached_timeframes = ["5m", "15m", "1h", "4h", "1d"]
        self.kline_cache_ttl = {
            "5m": 120,
            "15m": 300,
            "1h": 180,   # 3分钟
            "4h": 900,   # 15分钟
            "1d": 3600,  # 1小时
        }
        self._kline_cache: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self._intraday_cache: Dict[Tuple[str, str], Dict[str, Any]] = {}

    async def start(self) -> None:
        """启动后台采集任务"""
        if self._task and not self._task.done():
            self.logger.warning("数据采集任务已在运行")
            return

        self.running = True
        self._task = asyncio.create_task(self._collection_loop())
        self.logger.info("✓ [数据采集] 后台任务已启动（间隔: %s秒）", self.collection_interval)

        # 等待初始数据采集完成(至少一轮)
        await self._wait_for_initial_data()

    async def stop(self, timeout: float = 2.0) -> None:
        """
        停止后台采集任务

        Args:
            timeout: 等待任务结束的超时时间(秒)
        """
        self.running = False

        if self._task and not self._task.done():
            self.logger.info("正在停止数据采集任务...")
            self._task.cancel()
            try:
                await asyncio.wait_for(self._task, timeout=timeout)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

        self.logger.info("后台数据采集任务已停止")

    async def _wait_for_initial_data(self, max_wait: int = 15) -> None:
        """
        等待初始数据采集完成

        Args:
            max_wait: 最大等待时间(秒)
        """
        self.logger.debug("⏳ 等待初始数据采集完成...")
        elapsed = 0
        check_interval = 0.5

        while elapsed < max_wait:
            # 检查是否所有交易对都有数据
            if all(symbol in self._last_snapshots for symbol in self.symbols):
                self.logger.info("✅ 初始数据采集完成")
                return

            await asyncio.sleep(check_interval)
            elapsed += check_interval

        # 超时警告
        ready_count = len(self._last_snapshots)
        total_count = len(self.symbols)
        self.logger.warning(
            "初始数据采集超时，仅完成 %d/%d 个交易对",
            ready_count,
            total_count
        )

    async def _collection_loop(self) -> None:
        """数据采集主循环"""
        try:
            while self.running:
                try:
                    # 并发采集所有交易对的数据
                    tasks = [
                        self.collect_symbol_data(symbol)
                        for symbol in self.symbols
                    ]
                    results = await asyncio.gather(*tasks, return_exceptions=True)

                    # 检查采集结果
                    for symbol, result in zip(self.symbols, results):
                        if isinstance(result, Exception):
                            self.logger.error("采集 %s 数据失败: %s", symbol, result)

                    # 等待下一次采集 (使用可中断的 sleep)
                    await self._interruptible_sleep(self.collection_interval)

                except asyncio.CancelledError:
                    self.logger.info("数据采集任务被取消")
                    break
                except Exception as exc:
                    self.logger.error("数据采集循环错误: %s", exc, exc_info=True)
                    await self._interruptible_sleep(self.collection_interval)

        except Exception as e:
            self.logger.error("后台数据采集任务异常: %s", e, exc_info=True)
        finally:
            self.logger.info("后台数据采集任务已停止")

    async def _interruptible_sleep(self, seconds: float, check_interval: float = 0.1) -> None:
        """
        可中断的 sleep,定期检查 self.running 标志

        Args:
            seconds: 总共要 sleep 的秒数
            check_interval: 检查间隔(秒),默认 0.1 秒检查一次
        """
        elapsed = 0.0
        while elapsed < seconds and self.running:
            sleep_time = min(check_interval, seconds - elapsed)
            await asyncio.sleep(sleep_time)
            elapsed += sleep_time

    async def collect_symbol_data(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        采集单个交易对的数据

        Args:
            symbol: 交易对符号

        Returns:
            市场数据快照,包含市场上下文、ticker、技术指标等
        """
        try:
            # 采集最新行情 + 技术指标
            ticker = await self.market_collector.get_ticker(symbol)
            self.logger.debug("获取 %s 市场数据，最新价: %s", symbol, ticker.last)

            ohlcv = await self.market_collector.get_ohlcv(
                symbol, timeframe="1h", limit=200
            )
            if not ohlcv:
                self.logger.warning("%s 无可用的 K 线数据，跳过。", symbol)
                return None

            closes: List[Decimal] = [candle.close for candle in ohlcv]
            highs: List[Decimal] = [candle.high for candle in ohlcv]
            lows: List[Decimal] = [candle.low for candle in ohlcv]
            volumes: List[Decimal] = [candle.volume for candle in ohlcv]

            if len(closes) < 5:
                self.logger.warning("%s 的 K 线样本不足，跳过。", symbol)
                return None

            # 计算技术指标
            sma_fast = self.indicator_calculator.calculate_sma(closes, 12)
            sma_slow = self.indicator_calculator.calculate_sma(closes, 26)
            rsi_values = self.indicator_calculator.calculate_rsi(closes, 14)
            macd_data = self.indicator_calculator.calculate_macd(closes)

            # 计算ATR和ADX (趋势强度和波动率指标)
            atr_values = self.indicator_calculator.calculate_atr(highs, lows, closes, 14)
            adx_data = self.indicator_calculator.calculate_adx(highs, lows, closes, 14)

            last_close = closes[-1]
            previous_close = closes[-2]

            sma_fast_val = sma_fast[-1] if sma_fast else last_close
            sma_slow_val = sma_slow[-1] if sma_slow else last_close
            rsi_value = rsi_values[-1] if rsi_values else Decimal("50")
            macd_hist = (
                macd_data["histogram"][-1]
                if macd_data["histogram"]
                else Decimal("0")
            )

            # 提取ATR和ADX的最新值
            atr_value = atr_values[-1] if atr_values else Decimal("0")
            adx_value = adx_data["adx"][-1] if adx_data.get("adx") else Decimal("0")
            plus_di = adx_data["plus_di"][-1] if adx_data.get("plus_di") else Decimal("0")
            minus_di = adx_data["minus_di"][-1] if adx_data.get("minus_di") else Decimal("0")

            # 计算波动率
            prices_window = closes[-20:] if len(closes) >= 20 else closes
            volatility_float = (
                pstdev([float(price) for price in prices_window])
                if len(prices_window) > 1
                else 0.0
            )
            volatility = (
                Decimal(f"{volatility_float:.6f}") if volatility_float else Decimal("0")
            )

            # 判断市场状态
            if last_close > sma_slow_val:
                market_regime = "bull"
            elif last_close < sma_slow_val:
                market_regime = "bear"
            else:
                market_regime = "sideways"

            trend = (
                "up"
                if last_close > previous_close
                else "down"
                if last_close < previous_close
                else "neutral"
            )

            # 构建市场上下文
            market_context = MarketContext(
                timestamp=ticker.timestamp,
                dt=ticker.dt,
                market_regime=market_regime,
                volatility=volatility,
                trend=trend,
                recent_prices=prices_window[-10:],
                indicators={
                    "rsi": float(rsi_value),
                    "sma_fast": float(sma_fast_val),
                    "sma_slow": float(sma_slow_val),
                    "macd_hist": float(macd_hist),
                    "atr": float(atr_value),
                    "adx": float(adx_value),
                    "plus_di": float(plus_di),
                    "minus_di": float(minus_di),
                },
                recent_trades=[],
            )

            # 更新短期内存
            await self.short_term_memory.update_market_context(symbol, market_context)

            # 保存K线数据到数据库
            if self.save_klines and self.dao:
                try:
                    saved_count = await self.dao.save_klines(
                        symbol=symbol,
                        timeframe="1h",
                        klines=ohlcv
                    )
                    self.logger.debug(
                        "保存 %s 的 %d 根K线到数据库",
                        symbol,
                        saved_count
                    )
                except Exception as save_error:
                    self.logger.warning(
                        "保存K线数据失败 %s: %s",
                        symbol,
                        save_error
                    )

            # 构建并缓存快照
            volatility_state = self._volatility_label(float(volatility / last_close)) if last_close else "未知"
            volume_state = self._volume_label(volumes)
            support_info = self._calculate_support_resistance(ohlcv, last_close)

            snapshot = {
                "market_context": market_context,
                "ticker": ticker,
                "closes": closes,
                "sma_fast": sma_fast_val,
                "sma_slow": sma_slow_val,
                "rsi": rsi_value,
                "atr": atr_value,
                "adx": adx_value,
                "plus_di": plus_di,
                "minus_di": minus_di,
                "latest_price": last_close,
                "volatility_state": volatility_state,
                "volume_state": volume_state,
            }
            if support_info:
                snapshot.update(support_info)
            self._last_snapshots[symbol] = snapshot
            # 缓存1h K线数据，供其它模块复用
            self._cache_klines(symbol, "1h", ohlcv)
            await self._maybe_refresh_additional_timeframes(symbol)
            await self._augment_snapshot_with_intraday(symbol, snapshot)

            return snapshot

        except Exception as exc:
            # 网络错误很常见，只记录简短信息，下次采集会自动重试
            self.logger.warning("采集 %s 数据失败: %s (下次采集自动重试)", symbol, str(exc)[:100])
            return None

    def get_latest_snapshot(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        获取指定交易对的最新市场快照

        Args:
            symbol: 交易对符号

        Returns:
            最新的市场数据快照,如果不存在则返回 None
        """
        return self._last_snapshots.get(symbol)

    def get_all_snapshots(self) -> Dict[str, Dict[str, Any]]:
        """
        获取所有交易对的最新快照

        Returns:
            所有交易对的市场快照字典
        """
        return self._last_snapshots.copy()

    def has_data_for_symbol(self, symbol: str) -> bool:
        """
        检查是否已有指定交易对的数据

        Args:
            symbol: 交易对符号

        Returns:
            是否存在该交易对的数据
        """
        return symbol in self._last_snapshots

    def is_running(self) -> bool:
        """
        检查采集任务是否正在运行

        Returns:
            是否正在运行
        """
        return self.running and self._task is not None and not self._task.done()

    async def get_cached_klines(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 200,
        force_refresh: bool = False,
    ) -> List[Any]:
        """
        获取缓存的 K 线数据（必要时会刷新）
        """
        key = (symbol, timeframe)
        cache = self._kline_cache.get(key)

        if force_refresh or self._is_cache_expired(key):
            await self._refresh_kline_cache(symbol, timeframe)
            cache = self._kline_cache.get(key)

        if not cache:
            return []

        klines = cache.get("klines", [])
        if limit and len(klines) > limit:
            return klines[-limit:]
        return klines

    async def _augment_snapshot_with_intraday(self, symbol: str, snapshot: Dict[str, Any]) -> None:
        """为快照补充短周期行情"""
        try:
            short_summary = await self._get_intraday_summary(symbol, "5m")
            if short_summary:
                snapshot["short_term"] = short_summary
                self._intraday_cache[(symbol, "5m")] = short_summary
            mid_summary = await self._get_intraday_summary(symbol, "15m")
            if mid_summary:
                snapshot["mid_term"] = mid_summary
                self._intraday_cache[(symbol, "15m")] = mid_summary
        except Exception as exc:  # pylint:disable=broad-except
            self.logger.debug("补充短周期行情失败 %s: %s", symbol, exc)

    async def _get_intraday_summary(self, symbol: str, timeframe: str) -> Optional[Dict[str, Any]]:
        klines = await self.get_cached_klines(symbol, timeframe, limit=120)
        if not klines:
            klines = await self.get_cached_klines(
                symbol, timeframe, limit=120, force_refresh=True
            )
        if not klines:
            try:
                klines = await self.market_collector.get_ohlcv(symbol, timeframe=timeframe, limit=120)
                if klines:
                    self._cache_klines(symbol, timeframe, klines)
            except Exception as exc:  # pylint: disable=broad-except
                self.logger.debug("直接获取 %s %s K线失败: %s", symbol, timeframe, exc)
                return None

        if not klines or len(klines) < 30:
            return None

        closes = [candle.close for candle in klines]
        highs = [candle.high for candle in klines]
        lows = [candle.low for candle in klines]
        volumes = [candle.volume for candle in klines]

        rsi_value = self.indicator_calculator.calculate_rsi(closes, 14)[-1]
        ma20 = self.indicator_calculator.calculate_sma(closes, 20)[-1]
        atr_value = self.indicator_calculator.calculate_atr(highs, lows, closes, 14)[-1]
        adx_data = self.indicator_calculator.calculate_adx(highs, lows, closes, 14)
        adx_value = adx_data["adx"][-1] if adx_data.get("adx") else Decimal("0")

        price = closes[-1]
        price_vs_ma = self._price_vs_ma(price, ma20)
        vol_state = self._volatility_label(float(atr_value / price)) if price else "未知"
        volume_state = self._volume_label(volumes)

        return {
            "timeframe": timeframe,
            "price": float(price),
            "rsi": float(rsi_value),
            "ma20": float(ma20),
            "price_vs_ma20": price_vs_ma,
            "atr": float(atr_value),
            "volatility": vol_state,
            "volume_state": volume_state,
            "adx": float(adx_value),
        }

    def _price_vs_ma(self, price: Decimal, ma: Decimal) -> str:
        if price > ma:
            return "上方"
        if price < ma:
            return "下方"
        return "附近"

    def _volume_label(self, volumes: List[Decimal]) -> str:
        if not volumes:
            return "未知"
        recent = [float(v) for v in volumes[-20:] if v is not None]
        last = float(volumes[-1])
        if not recent:
            return "未知"
        avg = sum(recent) / len(recent)
        if avg == 0:
            return "未知"
        ratio = last / avg
        if ratio >= 1.3:
            return "放量"
        if ratio <= 0.7:
            return "缩量"
        return "正常"

    def _volatility_label(self, ratio: float) -> str:
        if ratio >= 0.02:
            return "极高"
        if ratio >= 0.01:
            return "偏高"
        if ratio >= 0.005:
            return "中性"
        return "低"

    def _calculate_support_resistance(
        self,
        ohlcv: List[Any],
        last_price: Decimal,
    ) -> Optional[Dict[str, Any]]:
        if not ohlcv or len(ohlcv) < 10 or not last_price:
            return None

        window = ohlcv[-40:]
        highs = [float(candle.high) for candle in window]
        lows = [float(candle.low) for candle in window]
        resistance = max(highs) if highs else None
        support = min(lows) if lows else None

        result: Dict[str, Any] = {}
        if support:
            result["support"] = support
            result["distance_to_support_pct"] = (
                float(((last_price - Decimal(str(support))) / last_price) * 100)
                if last_price and support
                else None
            )
        if resistance:
            result["resistance"] = resistance
            result["distance_to_resistance_pct"] = (
                float(((Decimal(str(resistance)) - last_price) / last_price) * 100)
                if last_price and resistance
                else None
            )
        return result or None

    def get_intraday_summary_cached(self, symbol: str, timeframe: str) -> Optional[Dict[str, Any]]:
        """提供给交易层获取最新的短周期摘要"""
        return self._intraday_cache.get((symbol, timeframe))

    def _cache_klines(self, symbol: str, timeframe: str, klines: List[Any]) -> None:
        """缓存K线数据（仅保留最近500根）"""
        if not klines:
            return
        key = (symbol, timeframe)
        max_length = 500
        trimmed = klines[-max_length:] if len(klines) > max_length else list(klines)
        self._kline_cache[key] = {
            "klines": trimmed,
            "updated_at": datetime.now(timezone.utc),
        }

    def _is_cache_expired(self, key: Tuple[str, str]) -> bool:
        cache = self._kline_cache.get(key)
        if not cache:
            return True
        ttl = self.kline_cache_ttl.get(key[1], 300)
        updated_at = cache.get("updated_at")
        if not updated_at:
            return True
        return (datetime.now(timezone.utc) - updated_at).total_seconds() > ttl

    async def _refresh_kline_cache(self, symbol: str, timeframe: str) -> None:
        try:
            klines = await self.market_collector.get_ohlcv(symbol, timeframe=timeframe, limit=200)
            if klines:
                self._cache_klines(symbol, timeframe, klines)
        except Exception as exc:  # pylint: disable=broad-except
            self.logger.debug("刷新 %s %s K线缓存失败: %s", symbol, timeframe, exc)

    async def _maybe_refresh_additional_timeframes(self, symbol: str) -> None:
        """按需刷新额外时间周期的K线缓存"""
        tasks = []
        for timeframe in self.cached_timeframes:
            if timeframe == self.primary_timeframe:
                continue
            key = (symbol, timeframe)
            if self._is_cache_expired(key):
                tasks.append(self._refresh_kline_cache(symbol, timeframe))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
