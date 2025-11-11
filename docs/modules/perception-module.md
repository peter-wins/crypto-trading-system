# 感知模块开发指南

本文档提供感知模块的详细开发指南，包括完整的代码示例和实现细节。

## 1. 模块概述

感知模块负责：
- 从交易所采集市场数据（ticker、OHLCV、订单簿）
- 计算技术指标（RSI、MACD、均线等）
- 数据验证和清洗
- 实时数据流处理

## 2. 市场数据采集器实现

### 2.1 基础接口

参考文档: `docs/prd/02-API-CONTRACTS.md` 第2.1章

### 2.2 CCXT市场数据采集器完整实现

```python
# src/perception/market_data.py

import asyncio
from typing import List, Optional, Callable
from datetime import datetime
from decimal import Decimal
import ccxt.async_support as ccxt

from src.models.market import OHLCVData, OrderBook, OrderBookLevel, Ticker
from src.core.config import ExchangeConfig
from src.core.logger import get_logger
from src.core.exceptions import (
    MarketDataError,
    ExchangeConnectionError,
    RateLimitError
)

logger = get_logger(__name__)


class CCXTMarketDataCollector:
    """
    CCXT-based market data collector.

    Supports multiple exchanges through unified CCXT interface.
    Implements rate limiting, retry logic, and error handling.
    """

    def __init__(self, exchange_config: ExchangeConfig):
        """
        Initialize market data collector.

        Args:
            exchange_config: Exchange configuration
        """
        self.config = exchange_config
        self.exchange: Optional[ccxt.Exchange] = None
        self._request_count = 0
        self._last_request_time = datetime.utcnow()

        # Rate limiting
        self.rate_limit_per_minute = exchange_config.rate_limit
        self.requests_this_minute = 0

        logger.info(
            f"Initialized market data collector for {exchange_config.name}"
        )

    async def __aenter__(self):
        """Async context manager entry"""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()

    async def connect(self) -> None:
        """
        Connect to exchange.

        Raises:
            ExchangeConnectionError: If connection fails
        """
        try:
            # Create exchange instance
            exchange_class = getattr(ccxt, self.config.name)

            self.exchange = exchange_class({
                'apiKey': self.config.api_key,
                'secret': self.config.api_secret,
                'password': self.config.password,
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'spot',
                }
            })

            # Set sandbox mode if testnet
            if self.config.testnet:
                self.exchange.set_sandbox_mode(True)
                logger.info(f"Using testnet for {self.config.name}")

            # Load markets
            await self.exchange.load_markets()

            logger.info(
                f"Connected to {self.config.name}, "
                f"loaded {len(self.exchange.markets)} markets"
            )

        except Exception as e:
            logger.error(f"Failed to connect to {self.config.name}: {e}")
            raise ExchangeConnectionError(
                f"Failed to connect to exchange",
                details={"exchange": self.config.name},
                original_exception=e
            )

    async def close(self) -> None:
        """Close exchange connection"""
        if self.exchange:
            await self.exchange.close()
            logger.info(f"Closed connection to {self.config.name}")

    async def _check_rate_limit(self) -> None:
        """Check and enforce rate limits"""
        now = datetime.utcnow()

        # Reset counter every minute
        if (now - self._last_request_time).total_seconds() > 60:
            self.requests_this_minute = 0
            self._last_request_time = now

        # Check if limit exceeded
        if self.requests_this_minute >= self.rate_limit_per_minute:
            wait_time = 60 - (now - self._last_request_time).total_seconds()
            if wait_time > 0:
                logger.warning(
                    f"Rate limit reached, waiting {wait_time:.1f}s"
                )
                await asyncio.sleep(wait_time)
                self.requests_this_minute = 0
                self._last_request_time = datetime.utcnow()

        self.requests_this_minute += 1

    async def get_ticker(self, symbol: str) -> Ticker:
        """
        Get ticker data for a symbol.

        Args:
            symbol: Trading pair (e.g., "BTC/USDT")

        Returns:
            Ticker object

        Raises:
            MarketDataError: If fetch fails
        """
        await self._check_rate_limit()

        try:
            logger.debug(f"Fetching ticker for {symbol}")

            ticker_data = await self.exchange.fetch_ticker(symbol)

            # Convert to our Ticker model
            ticker = Ticker(
                symbol=symbol,
                timestamp=ticker_data['timestamp'],
                datetime=datetime.fromtimestamp(ticker_data['timestamp'] / 1000),
                last=Decimal(str(ticker_data['last'])),
                bid=Decimal(str(ticker_data['bid'])) if ticker_data['bid'] else Decimal('0'),
                ask=Decimal(str(ticker_data['ask'])) if ticker_data['ask'] else Decimal('0'),
                high=Decimal(str(ticker_data['high'])) if ticker_data['high'] else Decimal('0'),
                low=Decimal(str(ticker_data['low'])) if ticker_data['low'] else Decimal('0'),
                volume=Decimal(str(ticker_data['baseVolume'])) if ticker_data['baseVolume'] else Decimal('0'),
                quote_volume=Decimal(str(ticker_data['quoteVolume'])) if ticker_data['quoteVolume'] else Decimal('0'),
                change_24h=Decimal(str(ticker_data['percentage'])) if ticker_data['percentage'] else Decimal('0')
            )

            logger.debug(
                f"Fetched ticker for {symbol}: "
                f"last={ticker.last}, volume={ticker.volume}"
            )

            return ticker

        except ccxt.RateLimitExceeded as e:
            raise RateLimitError(
                "Rate limit exceeded",
                details={"symbol": symbol, "exchange": self.config.name},
                original_exception=e
            )
        except Exception as e:
            logger.error(f"Failed to fetch ticker for {symbol}: {e}")
            raise MarketDataError(
                f"Failed to fetch ticker",
                details={"symbol": symbol, "exchange": self.config.name},
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
        Get OHLCV (candlestick) data.

        Args:
            symbol: Trading pair
            timeframe: Timeframe (1m, 5m, 15m, 1h, 4h, 1d)
            since: Start timestamp in milliseconds
            limit: Number of candles to fetch

        Returns:
            List of OHLCV data

        Raises:
            MarketDataError: If fetch fails
        """
        await self._check_rate_limit()

        try:
            logger.debug(
                f"Fetching OHLCV for {symbol}, "
                f"timeframe={timeframe}, limit={limit}"
            )

            ohlcv_raw = await self.exchange.fetch_ohlcv(
                symbol,
                timeframe=timeframe,
                since=since,
                limit=limit
            )

            # Convert to our OHLCV model
            ohlcv_list = []
            for candle in ohlcv_raw:
                timestamp, open_, high, low, close, volume = candle

                ohlcv = OHLCVData(
                    symbol=symbol,
                    timestamp=timestamp,
                    datetime=datetime.fromtimestamp(timestamp / 1000),
                    open=Decimal(str(open_)),
                    high=Decimal(str(high)),
                    low=Decimal(str(low)),
                    close=Decimal(str(close)),
                    volume=Decimal(str(volume))
                )
                ohlcv_list.append(ohlcv)

            logger.debug(f"Fetched {len(ohlcv_list)} candles for {symbol}")

            return ohlcv_list

        except ccxt.RateLimitExceeded as e:
            raise RateLimitError(
                "Rate limit exceeded",
                details={
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "exchange": self.config.name
                },
                original_exception=e
            )
        except Exception as e:
            logger.error(f"Failed to fetch OHLCV for {symbol}: {e}")
            raise MarketDataError(
                f"Failed to fetch OHLCV",
                details={
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "exchange": self.config.name
                },
                original_exception=e
            )

    async def get_orderbook(
        self,
        symbol: str,
        limit: int = 20
    ) -> OrderBook:
        """
        Get order book (market depth).

        Args:
            symbol: Trading pair
            limit: Number of levels to fetch

        Returns:
            OrderBook object

        Raises:
            MarketDataError: If fetch fails
        """
        await self._check_rate_limit()

        try:
            logger.debug(f"Fetching orderbook for {symbol}, limit={limit}")

            orderbook_raw = await self.exchange.fetch_order_book(
                symbol,
                limit=limit
            )

            # Convert to our model
            bids = [
                OrderBookLevel(
                    price=Decimal(str(price)),
                    amount=Decimal(str(amount))
                )
                for price, amount in orderbook_raw['bids']
            ]

            asks = [
                OrderBookLevel(
                    price=Decimal(str(price)),
                    amount=Decimal(str(amount))
                )
                for price, amount in orderbook_raw['asks']
            ]

            orderbook = OrderBook(
                symbol=symbol,
                timestamp=orderbook_raw['timestamp'],
                datetime=datetime.fromtimestamp(orderbook_raw['timestamp'] / 1000),
                bids=bids,
                asks=asks
            )

            logger.debug(
                f"Fetched orderbook for {symbol}: "
                f"spread={orderbook.get_spread()}"
            )

            return orderbook

        except ccxt.RateLimitExceeded as e:
            raise RateLimitError(
                "Rate limit exceeded",
                details={"symbol": symbol, "exchange": self.config.name},
                original_exception=e
            )
        except Exception as e:
            logger.error(f"Failed to fetch orderbook for {symbol}: {e}")
            raise MarketDataError(
                f"Failed to fetch orderbook",
                details={"symbol": symbol, "exchange": self.config.name},
                original_exception=e
            )

    async def subscribe_ticker(
        self,
        symbol: str,
        callback: Callable
    ) -> None:
        """
        Subscribe to real-time ticker updates (if exchange supports websocket).

        Args:
            symbol: Trading pair
            callback: Async callback function(ticker: Ticker)

        Note:
            This is a placeholder. Full websocket implementation
            requires exchange-specific handling.
        """
        # TODO: Implement websocket subscription
        logger.warning("Websocket subscription not yet implemented")

        # Fallback: polling
        while True:
            try:
                ticker = await self.get_ticker(symbol)
                await callback(ticker)
                await asyncio.sleep(1)  # Poll every second
            except Exception as e:
                logger.error(f"Error in ticker subscription: {e}")
                await asyncio.sleep(5)  # Wait before retry

    async def get_multiple_tickers(
        self,
        symbols: List[str]
    ) -> dict[str, Ticker]:
        """
        Get tickers for multiple symbols efficiently.

        Args:
            symbols: List of trading pairs

        Returns:
            Dictionary mapping symbol to Ticker
        """
        try:
            # Use fetch_tickers for efficiency if available
            if hasattr(self.exchange, 'fetch_tickers'):
                tickers_raw = await self.exchange.fetch_tickers(symbols)

                tickers = {}
                for symbol in symbols:
                    if symbol in tickers_raw:
                        data = tickers_raw[symbol]
                        tickers[symbol] = Ticker(
                            symbol=symbol,
                            timestamp=data['timestamp'],
                            datetime=datetime.fromtimestamp(data['timestamp'] / 1000),
                            last=Decimal(str(data['last'])),
                            bid=Decimal(str(data['bid'] or 0)),
                            ask=Decimal(str(data['ask'] or 0)),
                            high=Decimal(str(data['high'] or 0)),
                            low=Decimal(str(data['low'] or 0)),
                            volume=Decimal(str(data['baseVolume'] or 0)),
                            quote_volume=Decimal(str(data['quoteVolume'] or 0)),
                            change_24h=Decimal(str(data['percentage'] or 0))
                        )

                return tickers

            else:
                # Fallback: fetch individually
                tickers = {}
                for symbol in symbols:
                    tickers[symbol] = await self.get_ticker(symbol)
                return tickers

        except Exception as e:
            logger.error(f"Failed to fetch multiple tickers: {e}")
            raise MarketDataError(
                "Failed to fetch multiple tickers",
                details={"symbols": symbols},
                original_exception=e
            )
```

## 3. 技术指标计算器实现

### 3.1 使用pandas-ta实现

```python
# src/perception/indicators.py

from typing import List, Dict, Any
from decimal import Decimal
import pandas as pd
import pandas_ta as ta
import numpy as np

from src.core.logger import get_logger
from src.core.exceptions import DataCollectionError

logger = get_logger(__name__)


class PandasIndicatorCalculator:
    """
    Technical indicator calculator using pandas-ta.

    Provides common technical indicators for trading decisions.
    """

    def __init__(self):
        """Initialize indicator calculator"""
        logger.info("Initialized PandasIndicatorCalculator")

    def _to_series(self, prices: List[Decimal]) -> pd.Series:
        """Convert Decimal list to pandas Series"""
        return pd.Series([float(p) for p in prices])

    def _from_series(self, series: pd.Series) -> List[Decimal]:
        """Convert pandas Series to Decimal list"""
        return [Decimal(str(v)) if not pd.isna(v) else Decimal('0')
                for v in series]

    def calculate_sma(
        self,
        prices: List[Decimal],
        period: int
    ) -> List[Decimal]:
        """
        Calculate Simple Moving Average.

        Args:
            prices: Price series
            period: Period length

        Returns:
            SMA values
        """
        try:
            series = self._to_series(prices)
            sma = ta.sma(series, length=period)
            return self._from_series(sma)

        except Exception as e:
            logger.error(f"Failed to calculate SMA: {e}")
            raise DataCollectionError(
                "SMA calculation failed",
                details={"period": period},
                original_exception=e
            )

    def calculate_ema(
        self,
        prices: List[Decimal],
        period: int
    ) -> List[Decimal]:
        """
        Calculate Exponential Moving Average.

        Args:
            prices: Price series
            period: Period length

        Returns:
            EMA values
        """
        try:
            series = self._to_series(prices)
            ema = ta.ema(series, length=period)
            return self._from_series(ema)

        except Exception as e:
            logger.error(f"Failed to calculate EMA: {e}")
            raise DataCollectionError(
                "EMA calculation failed",
                details={"period": period},
                original_exception=e
            )

    def calculate_rsi(
        self,
        prices: List[Decimal],
        period: int = 14
    ) -> List[Decimal]:
        """
        Calculate Relative Strength Index.

        Args:
            prices: Price series
            period: Period length (default 14)

        Returns:
            RSI values (0-100)
        """
        try:
            series = self._to_series(prices)
            rsi = ta.rsi(series, length=period)
            return self._from_series(rsi)

        except Exception as e:
            logger.error(f"Failed to calculate RSI: {e}")
            raise DataCollectionError(
                "RSI calculation failed",
                details={"period": period},
                original_exception=e
            )

    def calculate_macd(
        self,
        prices: List[Decimal],
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9
    ) -> Dict[str, List[Decimal]]:
        """
        Calculate MACD (Moving Average Convergence Divergence).

        Args:
            prices: Price series
            fast_period: Fast EMA period
            slow_period: Slow EMA period
            signal_period: Signal line period

        Returns:
            Dictionary with 'macd', 'signal', 'histogram'
        """
        try:
            series = self._to_series(prices)

            macd_result = ta.macd(
                series,
                fast=fast_period,
                slow=slow_period,
                signal=signal_period
            )

            return {
                "macd": self._from_series(macd_result[f'MACD_{fast_period}_{slow_period}_{signal_period}']),
                "signal": self._from_series(macd_result[f'MACDs_{fast_period}_{slow_period}_{signal_period}']),
                "histogram": self._from_series(macd_result[f'MACDh_{fast_period}_{slow_period}_{signal_period}'])
            }

        except Exception as e:
            logger.error(f"Failed to calculate MACD: {e}")
            raise DataCollectionError(
                "MACD calculation failed",
                details={
                    "fast": fast_period,
                    "slow": slow_period,
                    "signal": signal_period
                },
                original_exception=e
            )

    def calculate_bollinger_bands(
        self,
        prices: List[Decimal],
        period: int = 20,
        std_dev: int = 2
    ) -> Dict[str, List[Decimal]]:
        """
        Calculate Bollinger Bands.

        Args:
            prices: Price series
            period: Period length
            std_dev: Standard deviation multiplier

        Returns:
            Dictionary with 'upper', 'middle', 'lower'
        """
        try:
            series = self._to_series(prices)

            bbands = ta.bbands(
                series,
                length=period,
                std=std_dev
            )

            return {
                "upper": self._from_series(bbands[f'BBU_{period}_{std_dev}.0']),
                "middle": self._from_series(bbands[f'BBM_{period}_{std_dev}.0']),
                "lower": self._from_series(bbands[f'BBL_{period}_{std_dev}.0'])
            }

        except Exception as e:
            logger.error(f"Failed to calculate Bollinger Bands: {e}")
            raise DataCollectionError(
                "Bollinger Bands calculation failed",
                details={"period": period, "std_dev": std_dev},
                original_exception=e
            )

    def calculate_atr(
        self,
        high: List[Decimal],
        low: List[Decimal],
        close: List[Decimal],
        period: int = 14
    ) -> List[Decimal]:
        """
        Calculate Average True Range (volatility indicator).

        Args:
            high: High prices
            low: Low prices
            close: Close prices
            period: Period length

        Returns:
            ATR values
        """
        try:
            df = pd.DataFrame({
                'high': [float(h) for h in high],
                'low': [float(l) for l in low],
                'close': [float(c) for c in close]
            })

            atr = ta.atr(
                df['high'],
                df['low'],
                df['close'],
                length=period
            )

            return self._from_series(atr)

        except Exception as e:
            logger.error(f"Failed to calculate ATR: {e}")
            raise DataCollectionError(
                "ATR calculation failed",
                details={"period": period},
                original_exception=e
            )

    def calculate_all_indicators(
        self,
        prices: List[Decimal],
        high: List[Decimal] = None,
        low: List[Decimal] = None
    ) -> Dict[str, Any]:
        """
        Calculate all common indicators at once.

        Args:
            prices: Close prices
            high: High prices (optional)
            low: Low prices (optional)

        Returns:
            Dictionary with all indicators
        """
        indicators = {}

        try:
            # Moving averages
            indicators['sma_20'] = self.calculate_sma(prices, 20)
            indicators['sma_50'] = self.calculate_sma(prices, 50)
            indicators['ema_12'] = self.calculate_ema(prices, 12)
            indicators['ema_26'] = self.calculate_ema(prices, 26)

            # Momentum indicators
            indicators['rsi'] = self.calculate_rsi(prices, 14)
            indicators['macd'] = self.calculate_macd(prices)

            # Volatility indicators
            indicators['bollinger'] = self.calculate_bollinger_bands(prices)

            # ATR if high/low provided
            if high and low:
                indicators['atr'] = self.calculate_atr(high, low, prices)

            logger.info("Calculated all indicators successfully")
            return indicators

        except Exception as e:
            logger.error(f"Failed to calculate indicators: {e}")
            raise DataCollectionError(
                "Indicator calculation failed",
                original_exception=e
            )
```

## 4. 数据验证和清洗

```python
# src/perception/validator.py

from typing import List, Optional
from decimal import Decimal
from datetime import datetime, timedelta

from src.models.market import OHLCVData, Ticker
from src.core.logger import get_logger
from src.core.exceptions import ValidationError

logger = get_logger(__name__)


class DataValidator:
    """Validate and clean market data"""

    def __init__(self):
        """Initialize validator"""
        self.logger = get_logger(__name__)

    def validate_ticker(self, ticker: Ticker) -> bool:
        """
        Validate ticker data.

        Args:
            ticker: Ticker object

        Returns:
            True if valid

        Raises:
            ValidationError: If data is invalid
        """
        # Check prices are positive
        if ticker.last <= 0:
            raise ValidationError(
                "Invalid ticker: last price must be positive",
                details={"symbol": ticker.symbol, "last": ticker.last}
            )

        # Check bid/ask spread is reasonable
        if ticker.bid > 0 and ticker.ask > 0:
            spread_pct = (ticker.ask - ticker.bid) / ticker.bid * 100
            if spread_pct > 10:  # More than 10% spread is suspicious
                self.logger.warning(
                    f"Large spread detected for {ticker.symbol}: {spread_pct:.2f}%"
                )

        # Check timestamp is recent (within 1 minute)
        now = datetime.utcnow()
        ticker_time = ticker.datetime
        if (now - ticker_time).total_seconds() > 60:
            self.logger.warning(
                f"Stale ticker data for {ticker.symbol}: "
                f"age={(now - ticker_time).total_seconds():.0f}s"
            )

        return True

    def validate_ohlcv(self, ohlcv: OHLCVData) -> bool:
        """
        Validate OHLCV data.

        Args:
            ohlcv: OHLCV object

        Returns:
            True if valid

        Raises:
            ValidationError: If data is invalid
        """
        # Check OHLC relationship
        if not (ohlcv.low <= ohlcv.open <= ohlcv.high and
                ohlcv.low <= ohlcv.close <= ohlcv.high):
            raise ValidationError(
                "Invalid OHLCV: price relationships violated",
                details={
                    "symbol": ohlcv.symbol,
                    "o": ohlcv.open,
                    "h": ohlcv.high,
                    "l": ohlcv.low,
                    "c": ohlcv.close
                }
            )

        # Check for zero volume (might indicate missing data)
        if ohlcv.volume == 0:
            self.logger.warning(
                f"Zero volume candle for {ohlcv.symbol} at {ohlcv.datetime}"
            )

        return True

    def detect_outliers(
        self,
        prices: List[Decimal],
        threshold: float = 3.0
    ) -> List[int]:
        """
        Detect price outliers using z-score.

        Args:
            prices: Price series
            threshold: Z-score threshold (default 3.0)

        Returns:
            List of outlier indices
        """
        import numpy as np

        price_array = np.array([float(p) for p in prices])
        mean = np.mean(price_array)
        std = np.std(price_array)

        if std == 0:
            return []

        z_scores = np.abs((price_array - mean) / std)
        outliers = np.where(z_scores > threshold)[0].tolist()

        if outliers:
            self.logger.warning(f"Detected {len(outliers)} outliers in price data")

        return outliers

    def fill_missing_values(
        self,
        ohlcv_list: List[OHLCVData],
        timeframe: str = "1h"
    ) -> List[OHLCVData]:
        """
        Fill missing candles with interpolated values.

        Args:
            ohlcv_list: List of OHLCV data
            timeframe: Timeframe string

        Returns:
            List with filled candles
        """
        if len(ohlcv_list) < 2:
            return ohlcv_list

        # Parse timeframe to seconds
        timeframe_seconds = self._parse_timeframe(timeframe)

        filled = []
        for i in range(len(ohlcv_list) - 1):
            current = ohlcv_list[i]
            next_candle = ohlcv_list[i + 1]

            filled.append(current)

            # Check for gap
            expected_next_time = current.timestamp + (timeframe_seconds * 1000)
            if next_candle.timestamp > expected_next_time:
                # Fill gap with previous close
                gap_count = (next_candle.timestamp - current.timestamp) // (timeframe_seconds * 1000) - 1

                for j in range(int(gap_count)):
                    filled_timestamp = current.timestamp + ((j + 1) * timeframe_seconds * 1000)
                    filled_candle = OHLCVData(
                        symbol=current.symbol,
                        timestamp=filled_timestamp,
                        datetime=datetime.fromtimestamp(filled_timestamp / 1000),
                        open=current.close,
                        high=current.close,
                        low=current.close,
                        close=current.close,
                        volume=Decimal('0')
                    )
                    filled.append(filled_candle)

        filled.append(ohlcv_list[-1])

        if len(filled) > len(ohlcv_list):
            self.logger.info(f"Filled {len(filled) - len(ohlcv_list)} missing candles")

        return filled

    def _parse_timeframe(self, timeframe: str) -> int:
        """Parse timeframe string to seconds"""
        unit = timeframe[-1]
        value = int(timeframe[:-1])

        if unit == 'm':
            return value * 60
        elif unit == 'h':
            return value * 3600
        elif unit == 'd':
            return value * 86400
        else:
            return 3600  # Default 1 hour
```

## 5. 使用示例

```python
# Example usage of perception module

import asyncio
from src.core.config import get_config
from src.perception.market_data import CCXTMarketDataCollector
from src.perception.indicators import PandasIndicatorCalculator
from src.perception.validator import DataValidator


async def main():
    # Initialize
    config = get_config()
    exchange_config = config.get_exchange_config("binance")

    # Create collector
    async with CCXTMarketDataCollector(exchange_config) as collector:
        # Fetch ticker
        ticker = await collector.get_ticker("BTC/USDT")
        print(f"BTC/USDT: ${ticker.last}")

        # Fetch OHLCV
        ohlcv_list = await collector.get_ohlcv(
            "BTC/USDT",
            timeframe="1h",
            limit=100
        )
        print(f"Fetched {len(ohlcv_list)} candles")

        # Calculate indicators
        calculator = PandasIndicatorCalculator()
        closes = [candle.close for candle in ohlcv_list]

        rsi = calculator.calculate_rsi(closes)
        print(f"Current RSI: {rsi[-1]}")

        macd = calculator.calculate_macd(closes)
        print(f"MACD: {macd['macd'][-1]}")

        # Validate data
        validator = DataValidator()
        for candle in ohlcv_list:
            validator.validate_ohlcv(candle)

        print("All data validated successfully")


if __name__ == "__main__":
    asyncio.run(main())
```

## 6. 测试

```python
# tests/perception/test_market_data.py

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, Mock

from src.perception.market_data import CCXTMarketDataCollector
from src.core.config import ExchangeConfig


@pytest.fixture
def exchange_config():
    return ExchangeConfig(
        name="binance",
        api_key="test_key",
        api_secret="test_secret",
        testnet=True
    )


@pytest.mark.asyncio
async def test_connect(exchange_config):
    """Test exchange connection"""
    collector = CCXTMarketDataCollector(exchange_config)

    # Mock exchange
    collector.exchange = Mock()
    collector.exchange.load_markets = AsyncMock()
    collector.exchange.markets = {"BTC/USDT": {}}

    await collector.connect()

    assert collector.exchange is not None


@pytest.mark.asyncio
async def test_get_ticker(exchange_config):
    """Test ticker fetching"""
    collector = CCXTMarketDataCollector(exchange_config)

    # Mock exchange response
    collector.exchange = Mock()
    collector.exchange.fetch_ticker = AsyncMock(return_value={
        'symbol': 'BTC/USDT',
        'timestamp': 1704067200000,
        'last': 45000,
        'bid': 44999,
        'ask': 45001,
        'high': 46000,
        'low': 44000,
        'baseVolume': 1000,
        'quoteVolume': 45000000,
        'percentage': 2.5
    })

    ticker = await collector.get_ticker("BTC/USDT")

    assert ticker.symbol == "BTC/USDT"
    assert ticker.last == Decimal("45000")
    assert ticker.change_24h == Decimal("2.5")
```

## 7. 性能优化建议

1. **批量获取**：使用 `get_multiple_tickers` 而不是循环调用
2. **缓存**：对不常变化的数据使用Redis缓存
3. **并发**：使用 `asyncio.gather` 并行获取多个symbol
4. **连接池**：复用exchange连接
5. **Websocket**：对实时数据使用websocket而非轮询

## 8. 注意事项

1. **错误处理**：所有外部API调用都要有错误处理和重试
2. **速率限制**：严格遵守交易所API限流规则
3. **数据验证**：始终验证数据完整性
4. **测试网**：开发阶段使用testnet
5. **日志**：详细记录所有API调用用于调试
