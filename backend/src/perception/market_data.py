"""
市场数据采集模块

基于 CCXT 的通用市场数据采集器，支持所有 CCXT 交易所。
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Callable
import ccxt.async_support as ccxt

from src.core.logger import get_logger
from src.core.exceptions import DataCollectionError
from src.models.market import OHLCVData, OrderBook, OrderBookLevel, Ticker


logger = get_logger(__name__)

class CCXTMarketDataCollector:
    """基于CCXT的市场数据采集器"""

    def __init__(self, exchange_id: str, config: dict = None):
        """
        初始化数据采集器

        Args:
            exchange_id: 交易所ID（如 hyperliquid, binance, okx等）
            config: CCXT配置字典
        """
        self.exchange_id = exchange_id
        self.config = config or {}
        self.exchange: Optional[ccxt.Exchange] = None
        self.logger = logger

    async def initialize(self) -> None:
        """初始化交易所连接"""
        try:
            # 动态获取交易所类
            exchange_class = getattr(ccxt, self.exchange_id)
            self.exchange = exchange_class(self.config)
            self._enable_sandbox_if_needed()

            # 加载市场信息
            await self.exchange.load_markets()

            self.logger.info(
                f"Initialized {self.exchange_id} market data collector"
            )
        except Exception as e:
            raise DataCollectionError(
                message=f"Failed to initialize {self.exchange_id}",
                details={"exchange_id": self.exchange_id},
                original_exception=e
            )

    async def close(self) -> None:
        """关闭交易所连接"""
        if self.exchange:
            await self.exchange.close()
            self.logger.info(f"Closed {self.exchange_id} connection")
            self.exchange = None

    def _enable_sandbox_if_needed(self) -> None:
        """在配置允许的情况下启用 CCXT Sandbox/Testnet 模式"""
        if not self.exchange:
            return

        testnet_flag = bool(
            self.config.get("testnet")
            or self.config.get("sandboxMode")
            or self.config.get("options", {}).get("testnet")
        )

        if testnet_flag and hasattr(self.exchange, "set_sandbox_mode"):
            try:
                self.exchange.set_sandbox_mode(True)
                self.logger.info("Enabled sandbox mode for %s", self.exchange_id)
            except Exception as exc:  # pylint: disable=broad-except
                self.logger.warning(
                    "Failed to enable sandbox mode on %s: %s",
                    self.exchange_id,
                    exc,
                )

    @staticmethod
    def _safe_decimal(value: Any, *, fallback: Any) -> Decimal:
        """
        安全地将值转换为 Decimal。当主值不可用时尝试使用 fallback。
        """
        candidates = (value, fallback, "0")
        for candidate in candidates:
            if candidate in (None, "", "null"):
                continue
            try:
                return Decimal(str(candidate))
            except (InvalidOperation, ValueError, TypeError):
                continue
        return Decimal("0")

    @staticmethod
    def _extract_timestamp(ticker_data: dict) -> int:
        """
        解析 ticker 数据中的毫秒时间戳，默认回退到当前时间。
        """
        raw_timestamp = (
            ticker_data.get("timestamp")
            or ticker_data.get("info", {}).get("closeTime")
            or ticker_data.get("info", {}).get("time")
        )
        if raw_timestamp is not None:
            for converter in (int, float):
                try:
                    return int(converter(raw_timestamp))
                except (ValueError, TypeError):
                    continue
        return int(datetime.now().timestamp() * 1000)

    async def get_ticker(self, symbol: str) -> Ticker:
        """
        获取ticker数据

        Args:
            symbol: 交易对，如 "BTC/USDT"

        Returns:
            Ticker对象

        Raises:
            DataCollectionError: 数据采集失败
        """
        try:
            if not self.exchange:
                await self.initialize()

            ticker_data = await self.exchange.fetch_ticker(symbol)
            timestamp = self._extract_timestamp(ticker_data)

            last_price = self._safe_decimal(
                ticker_data.get("last")
                or ticker_data.get("close")
                or ticker_data.get("info", {}).get("lastPrice"),
                fallback="0",
            )
            bid = self._safe_decimal(ticker_data.get("bid"), fallback=last_price)
            ask = self._safe_decimal(ticker_data.get("ask"), fallback=last_price)
            high = self._safe_decimal(ticker_data.get("high"), fallback=last_price)
            low = self._safe_decimal(ticker_data.get("low"), fallback=last_price)
            base_volume = self._safe_decimal(
                ticker_data.get("baseVolume")
                or ticker_data.get("volume")
                or ticker_data.get("info", {}).get("volume"),
                fallback="0",
            )
            quote_volume = self._safe_decimal(
                ticker_data.get("quoteVolume")
                or ticker_data.get("info", {}).get("quoteVolume"),
                fallback="0",
            )
            change_24h = self._safe_decimal(
                ticker_data.get("percentage")
                or ticker_data.get("info", {}).get("priceChangePercent"),
                fallback="0",
            )

            return Ticker(
                symbol=symbol,
                timestamp=timestamp,
                dt=datetime.fromtimestamp(timestamp / 1000),
                last=last_price,
                bid=bid,
                ask=ask,
                high=high,
                low=low,
                volume=base_volume,
                quote_volume=quote_volume,
                change_24h=change_24h
            )
        except Exception as e:
            raise DataCollectionError(
                message=f"Failed to fetch ticker for {symbol}",
                details={"symbol": symbol, "exchange": self.exchange_id},
                original_exception=e
            )

    async def get_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1h",
        since: Optional[int] = None,
        limit: int = 100
    ) -> List[OHLCVData]:
        """
        获取K线数据

        Args:
            symbol: 交易对
            timeframe: 时间周期，如 "1m", "5m", "1h", "1d"
            since: 起始时间戳(毫秒)
            limit: 数量限制

        Returns:
            OHLCV数据列表

        Raises:
            DataCollectionError: 数据采集失败
        """
        try:
            if not self.exchange:
                await self.initialize()

            ohlcv_data = await self.exchange.fetch_ohlcv(
                symbol, timeframe, since, limit
            )

            result = []
            for candle in ohlcv_data:
                timestamp, open_price, high, low, close, volume = candle
                result.append(OHLCVData(
                    symbol=symbol,
                    timestamp=timestamp,
                    dt=datetime.fromtimestamp(timestamp / 1000),
                    open=Decimal(str(open_price)),
                    high=Decimal(str(high)),
                    low=Decimal(str(low)),
                    close=Decimal(str(close)),
                    volume=Decimal(str(volume))
                ))

            return result
        except Exception as e:
            raise DataCollectionError(
                message=f"Failed to fetch OHLCV for {symbol}",
                details={
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "exchange": self.exchange_id
                },
                original_exception=e
            )

    async def get_orderbook(
        self,
        symbol: str,
        limit: int = 20
    ) -> OrderBook:
        """
        获取订单簿

        Args:
            symbol: 交易对
            limit: 深度限制

        Returns:
            OrderBook对象

        Raises:
            DataCollectionError: 数据采集失败
        """
        try:
            if not self.exchange:
                await self.initialize()

            orderbook_data = await self.exchange.fetch_order_book(symbol, limit)

            bids = [
                OrderBookLevel(
                    price=Decimal(str(bid[0])),
                    amount=Decimal(str(bid[1]))
                )
                for bid in orderbook_data["bids"]
            ]

            asks = [
                OrderBookLevel(
                    price=Decimal(str(ask[0])),
                    amount=Decimal(str(ask[1]))
                )
                for ask in orderbook_data["asks"]
            ]

            timestamp = orderbook_data.get("timestamp", int(datetime.now().timestamp() * 1000))

            return OrderBook(
                symbol=symbol,
                timestamp=timestamp,
                dt=datetime.fromtimestamp(timestamp / 1000),
                bids=bids,
                asks=asks
            )
        except Exception as e:
            raise DataCollectionError(
                message=f"Failed to fetch orderbook for {symbol}",
                details={"symbol": symbol, "exchange": self.exchange_id},
                original_exception=e
            )

    async def subscribe_ticker(
        self,
        symbol: str,
        callback: Callable[[Ticker], None]
    ) -> None:
        """
        订阅ticker实时数据（轮询实现）

        Args:
            symbol: 交易对
            callback: 回调函数，签名: async def callback(ticker: Ticker)

        Note:
            这是一个轮询实现。如需真实WebSocket，需要使用ccxt.pro
        """
        try:
            self.logger.info(f"Starting ticker subscription for {symbol}")

            while True:
                ticker = await self.get_ticker(symbol)
                await callback(ticker)
                await asyncio.sleep(1)  # 每秒更新一次

        except asyncio.CancelledError:
            self.logger.info(f"Ticker subscription cancelled for {symbol}")
        except Exception as e:
            self.logger.error(
                f"Error in ticker subscription for {symbol}: {e}",
                exc_info=True
            )

    async def get_available_symbols(self) -> List[str]:
        """
        获取可用交易对列表

        Returns:
            交易对列表
        """
        try:
            if not self.exchange:
                await self.initialize()

            return list(self.exchange.markets.keys())
        except Exception as e:
            raise DataCollectionError(
                message=f"Failed to get available symbols",
                details={"exchange": self.exchange_id},
                original_exception=e
            )

    async def get_exchange_status(self) -> dict:
        """
        获取交易所状态

        Returns:
            状态信息字典
        """
        try:
            if not self.exchange:
                await self.initialize()

            status = await self.exchange.fetch_status()
            return {
                "status": status.get("status", "unknown"),
                "updated": status.get("updated", None),
                "eta": status.get("eta", None),
                "url": status.get("url", None)
            }
        except Exception as e:
            self.logger.warning(f"Failed to get exchange status: {e}")
            return {"status": "unknown"}
