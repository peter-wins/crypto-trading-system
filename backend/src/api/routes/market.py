"""
市场数据API路由
"""

from typing import List
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from src.core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


# ===== 响应模型 =====

class TickerResponse(BaseModel):
    """Ticker响应"""
    symbol: str
    timestamp: int
    datetime: str
    last: float
    bid: float
    ask: float
    high: float
    low: float
    volume: float
    change_24h: float | None = None
    change_percentage_24h: float | None = None


class OHLCVResponse(BaseModel):
    """K线响应"""
    symbol: str
    timestamp: int
    datetime: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class OrderBookLevelResponse(BaseModel):
    """订单簿层级"""
    price: float
    amount: float


class OrderBookResponse(BaseModel):
    """订单簿响应"""
    symbol: str
    timestamp: int
    bids: List[OrderBookLevelResponse]
    asks: List[OrderBookLevelResponse]


# ===== Mock数据生成器 =====

def create_mock_ticker(symbol: str = "BTC/USDT") -> TickerResponse:
    """创建模拟Ticker数据"""
    import random
    base_price = 46500.0 if "BTC" in symbol else 2600.0
    spread = base_price * 0.0001

    now = datetime.now(timezone.utc)
    return TickerResponse(
        symbol=symbol,
        timestamp=int(now.timestamp() * 1000),
        datetime=now.isoformat(),
        last=base_price + random.uniform(-50, 50),
        bid=base_price - spread/2,
        ask=base_price + spread/2,
        high=base_price + random.uniform(100, 200),
        low=base_price - random.uniform(100, 200),
        volume=random.uniform(1000, 5000),
        change_24h=random.uniform(-500, 500),
        change_percentage_24h=random.uniform(-2, 2),
    )


def create_mock_ohlcv(symbol: str, timeframe: str, limit: int) -> List[OHLCVResponse]:
    """创建模拟K线数据"""
    import random
    base_price = 46500.0 if "BTC" in symbol else 2600.0

    result = []
    now = datetime.now(timezone.utc)

    # 根据时间周期计算时间间隔
    intervals = {
        "1m": 60,
        "5m": 300,
        "15m": 900,
        "1h": 3600,
        "4h": 14400,
        "1d": 86400,
    }
    interval = intervals.get(timeframe, 3600)

    for i in range(limit):
        timestamp = int((now.timestamp() - interval * (limit - i)) * 1000)
        dt = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)

        open_price = base_price + random.uniform(-100, 100)
        close_price = open_price + random.uniform(-50, 50)
        high_price = max(open_price, close_price) + random.uniform(0, 30)
        low_price = min(open_price, close_price) - random.uniform(0, 30)

        result.append(OHLCVResponse(
            symbol=symbol,
            timestamp=timestamp,
            datetime=dt.isoformat(),
            open=open_price,
            high=high_price,
            low=low_price,
            close=close_price,
            volume=random.uniform(100, 1000),
        ))

    return result


def create_mock_orderbook(symbol: str, limit: int) -> OrderBookResponse:
    """创建模拟订单簿"""
    import random
    base_price = 46500.0 if "BTC" in symbol else 2600.0

    bids = []
    asks = []

    for i in range(limit):
        bid_price = base_price - (i + 1) * base_price * 0.0001
        ask_price = base_price + (i + 1) * base_price * 0.0001

        bids.append(OrderBookLevelResponse(
            price=bid_price,
            amount=random.uniform(0.1, 2.0),
        ))

        asks.append(OrderBookLevelResponse(
            price=ask_price,
            amount=random.uniform(0.1, 2.0),
        ))

    now = datetime.now(timezone.utc)
    return OrderBookResponse(
        symbol=symbol,
        timestamp=int(now.timestamp() * 1000),
        bids=bids,
        asks=asks,
    )


# ===== 辅助函数 =====

def normalize_symbol(symbol: str) -> str:
    """
    标准化交易对符号

    将各种格式转换为Redis中使用的格式: BTC/USDT:USDT
    """
    # 移除所有空格
    symbol = symbol.strip()

    # 如果已经是标准格式，直接返回
    if ':' in symbol and '/' in symbol:
        return symbol

    # 常见的交易对映射
    symbol_map = {
        'BTCUSDT': 'BTC/USDT:USDT',
        'ETHUSDT': 'ETH/USDT:USDT',
        'BTC': 'BTC/USDT:USDT',
        'ETH': 'ETH/USDT:USDT',
    }

    return symbol_map.get(symbol, symbol)


# ===== API端点 =====

@router.get("/market/{symbol}/ticker", response_model=TickerResponse)
async def get_ticker(symbol: str):
    """
    获取Ticker数据

    返回指定交易对的最新价格信息
    """
    logger.info(f"API: 获取Ticker {symbol}")

    try:
        # 标准化symbol格式
        normalized_symbol = normalize_symbol(symbol)
        logger.debug(f"Normalized symbol: {symbol} -> {normalized_symbol}")

        # 从Redis短期内存读取真实市场数据
        from src.api.server import get_app_state
        from src.memory.short_term import RedisShortTermMemory

        app_state = get_app_state()
        redis_memory = app_state.get("redis_memory")

        if not redis_memory:
            logger.warning("Redis not initialized, returning mock data")
            return create_mock_ticker(symbol)

        # 获取市场上下文数据
        market_context = await redis_memory.get_market_context(normalized_symbol)

        if not market_context:
            logger.warning(f"No market data found for {normalized_symbol}, returning mock data")
            return create_mock_ticker(symbol)

        # 转换为Ticker响应格式
        recent_prices = market_context.recent_prices
        if not recent_prices:
            logger.warning(f"No recent prices for {normalized_symbol}, returning mock data")
            return create_mock_ticker(symbol)

        last_price = float(recent_prices[-1])
        high_price = max(float(p) for p in recent_prices)
        low_price = min(float(p) for p in recent_prices)

        # 从币安API获取真实的24小时涨跌幅数据（带缓存）
        change_24h = 0
        change_percentage_24h = 0

        try:
            # 将symbol转换为币安格式 (BTC/USDT:USDT -> BTCUSDT)
            binance_symbol = normalized_symbol.replace('/', '').replace(':USDT', '')

            # 先尝试从Redis缓存获取
            cache_key = f"binance_24h_ticker:{binance_symbol}"
            cached_data = None

            if redis_memory:
                try:
                    cached_data = await redis_memory.redis.get(cache_key)
                    if cached_data:
                        import json
                        data = json.loads(cached_data)
                        change_24h = float(data.get('priceChange', 0))
                        change_percentage_24h = float(data.get('priceChangePercent', 0))
                        logger.debug(f"24h change from cache: {normalized_symbol} ({change_percentage_24h:.2f}%)")
                except Exception as e:
                    logger.debug(f"Failed to get from cache: {e}")

            # 如果缓存不存在，调用币安API
            if not cached_data:
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    url = f"https://api.binance.com/api/v3/ticker/24hr?symbol={binance_symbol}"
                    async with session.get(url) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            change_24h = float(data.get('priceChange', 0))
                            change_percentage_24h = float(data.get('priceChangePercent', 0))
                            logger.debug(
                                f"24h change from Binance API: {normalized_symbol} "
                                f"({change_percentage_24h:.2f}%)"
                            )

                            # 缓存到Redis，30秒过期
                            if redis_memory:
                                try:
                                    import json
                                    await redis_memory.redis.setex(
                                        cache_key,
                                        30,  # 30秒缓存
                                        json.dumps({
                                            'priceChange': data.get('priceChange'),
                                            'priceChangePercent': data.get('priceChangePercent')
                                        })
                                    )
                                except Exception as e:
                                    logger.debug(f"Failed to cache: {e}")
                        else:
                            logger.warning(f"Failed to get 24h ticker from Binance: {resp.status}")
        except Exception as e:
            logger.warning(f"Failed to get 24h change from Binance API: {e}")
            # 如果API调用失败，保持默认值 0

        timestamp = market_context.timestamp
        dt = market_context.dt.isoformat() if hasattr(market_context.dt, 'isoformat') else str(market_context.dt)

        return TickerResponse(
            symbol=symbol,
            timestamp=timestamp,
            datetime=dt,
            last=last_price,
            bid=last_price * 0.9999,  # 模拟买价
            ask=last_price * 1.0001,  # 模拟卖价
            high=high_price,
            low=low_price,
            volume=0.0,  # Redis中没有存储成交量
            change_24h=change_24h,
            change_percentage_24h=change_percentage_24h,
        )

    except Exception as e:
        logger.error(f"获取Ticker失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/market/{symbol}/ohlcv", response_model=List[OHLCVResponse])
async def get_ohlcv(
    symbol: str,
    timeframe: str = Query("1h", description="时间周期: 1m, 5m, 15m, 1h, 4h, 1d"),
    limit: int = Query(100, ge=1, le=1000, description="数量限制"),
):
    """
    获取K线数据

    返回指定交易对的历史K线数据
    """
    logger.info(f"API: 获取K线 {symbol} {timeframe} limit={limit}")

    try:
        # TODO: 集成真实的市场数据采集器
        # from src.services.market_data import MarketDataCollector
        # collector = MarketDataCollector()
        # ohlcv = await collector.get_ohlcv(symbol, timeframe, limit=limit)
        # return [convert_ohlcv_to_response(candle) for candle in ohlcv]

        # 临时返回Mock数据
        return create_mock_ohlcv(symbol, timeframe, limit)

    except Exception as e:
        logger.error(f"获取K线失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/market/{symbol}/orderbook", response_model=OrderBookResponse)
async def get_orderbook(
    symbol: str,
    limit: int = Query(20, ge=1, le=100, description="深度限制"),
):
    """
    获取订单簿

    返回指定交易对的买卖盘数据
    """
    logger.info(f"API: 获取订单簿 {symbol} limit={limit}")

    try:
        # 标准化symbol并尝试获取真实价格
        normalized_symbol = normalize_symbol(symbol)

        from src.api.server import get_app_state
        app_state = get_app_state()
        redis_memory = app_state.get("redis_memory")

        base_price = 46500.0  # 默认价格

        # 尝试从Redis获取真实价格
        if redis_memory:
            try:
                market_context = await redis_memory.get_market_context(normalized_symbol)
                if market_context and market_context.recent_prices:
                    base_price = float(market_context.recent_prices[-1])
                    logger.debug(f"Using real price {base_price} for orderbook")
            except Exception as e:
                logger.warning(f"Failed to get real price for orderbook: {e}")

        # 基于真实价格生成模拟订单簿
        import random
        now = datetime.now(timezone.utc)

        bids = []
        asks = []

        for i in range(limit):
            bid_price = base_price - (i + 1) * base_price * 0.0001
            ask_price = base_price + (i + 1) * base_price * 0.0001

            bids.append(OrderBookLevelResponse(
                price=bid_price,
                amount=random.uniform(0.1, 2.0),
            ))

            asks.append(OrderBookLevelResponse(
                price=ask_price,
                amount=random.uniform(0.1, 2.0),
            ))

        return OrderBookResponse(
            symbol=symbol,
            timestamp=int(now.timestamp() * 1000),
            bids=bids,
            asks=asks,
        )

    except Exception as e:
        logger.error(f"获取订单簿失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/market/tickers", response_model=List[TickerResponse])
async def get_multiple_tickers(symbols: List[str]):
    """
    批量获取Ticker

    返回多个交易对的Ticker数据
    """
    logger.info(f"API: 批量获取Ticker {symbols}")

    try:
        # 批量获取每个symbol的ticker
        tickers = []
        for symbol in symbols:
            try:
                ticker = await get_ticker(symbol)
                tickers.append(ticker)
            except Exception as e:
                logger.error(f"获取 {symbol} ticker失败: {e}")
                # 失败时返回mock数据
                tickers.append(create_mock_ticker(symbol))

        return tickers

    except Exception as e:
        logger.error(f"批量获取Ticker失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
