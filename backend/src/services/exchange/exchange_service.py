"""
Unified Exchange Service.

Provides a centralized interface for all exchange API interactions.
Implements rate limiting, retry logic, and error handling.
"""

from typing import Dict, List, Optional, Any
import ccxt.async_support as ccxt

from src.core.config import get_config
from src.core.logger import get_logger
from src.core.exceptions import ExchangeConnectionError
from src.services.exchange.rate_limiter import get_rate_limiters
from src.services.exchange.decorators import api_call, cached

logger = get_logger(__name__)

# Binance USDM 期货测试网 API URLs (官方文档: https://demo-fapi.binance.com)
BINANCE_USDM_TESTNET_API: Dict[str, str] = {
    "fapiPublic": "https://demo-fapi.binance.com/fapi/v1",
    "fapiPublicV2": "https://demo-fapi.binance.com/fapi/v2",
    "fapiPublicV3": "https://demo-fapi.binance.com/fapi/v3",
    "fapiPrivate": "https://demo-fapi.binance.com/fapi/v1",
    "fapiPrivateV2": "https://demo-fapi.binance.com/fapi/v2",
    "fapiPrivateV3": "https://demo-fapi.binance.com/fapi/v3",
}


class ExchangeService:
    """
    统一的交易所服务（单例模式）

    提供所有交易所API的统一接口，包括：
    - 市场数据获取
    - 账户信息查询
    - 订单管理
    - 持仓管理

    Features:
    - 自动限流
    - 自动重试
    - 连接池管理
    - 统一错误处理
    - 日志记录
    """

    _instance: Optional['ExchangeService'] = None

    def __new__(cls):
        """单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """初始化交易所服务"""
        if self._initialized:
            return

        self.config = get_config()
        self._exchange: Optional[ccxt.Exchange] = None
        self._rate_limiters = get_rate_limiters()

        # 根据配置决定使用哪个交易所
        # 如果启用了期货模式，使用 binanceusdm，否则使用 binance
        if self.config.binance_futures:
            self._exchange_name = "binanceusdm"
        else:
            self._exchange_name = "binance"

        logger.info(f"ExchangeService initialized for {self._exchange_name} (futures={self.config.binance_futures})")
        self._initialized = True

    @property
    def exchange_name(self) -> str:
        """当前所使用的交易所标识"""
        return self._exchange_name

    async def _get_exchange(self) -> ccxt.Exchange:
        """
        获取exchange实例（懒加载 + 连接复用）

        Returns:
            ccxt.Exchange实例
        """
        if self._exchange is None:
            try:
                # 根据配置创建交易所实例
                exchange_class = getattr(ccxt, self._exchange_name)

                # 构建配置
                exchange_config = {
                    'apiKey': self.config.binance_api_key,
                    'secret': self.config.binance_api_secret,
                    'enableRateLimit': False,  # 我们自己实现限流
                    'options': {
                        'adjustForTimeDifference': True,
                    }
                }

                # 期货模式的额外配置
                if self.config.binance_futures:
                    exchange_config['options']['defaultType'] = 'future'
                    exchange_config['options']['defaultMarket'] = 'future'

                # Testnet 配置 - 对于 binanceusdm，不能使用 testnet=True
                # 需要手动设置 API URLs
                if self.config.binance_testnet:
                    if self._exchange_name == "binanceusdm":
                        # Binance USDM 期货测试网需要手动设置 URLs
                        exchange_config['options']['testnet'] = True
                        # 不设置 testnet=True，避免触发 CCXT 的 sandbox 模式
                    else:
                        # 其他交易所可以使用标准 testnet 模式
                        exchange_config['testnet'] = True
                        exchange_config['options']['testnet'] = True

                self._exchange = exchange_class(exchange_config)

                # 对于 binanceusdm testnet，需要手动替换 API URLs
                if self._exchange_name == "binanceusdm" and self.config.binance_testnet:
                    self._exchange.urls.setdefault("api", {})
                    self._exchange.urls["api"].update(BINANCE_USDM_TESTNET_API.copy())
                    self._exchange.isSandboxModeEnabled = False
                    self._exchange.options = self._exchange.options or {}
                    self._exchange.options["disableFuturesSandboxWarning"] = True
                    logger.info("已切换到 Binance USDM 测试网接口")

                # 测试连接
                await self._exchange.load_markets()
                logger.info(
                    f"Exchange connection established: {self._exchange_name} "
                    f"(testnet={self.config.binance_testnet}, futures={self.config.binance_futures})"
                )

            except Exception as e:
                logger.error(f"Failed to create exchange instance: {str(e)}")
                raise ExchangeConnectionError(f"Failed to connect to exchange: {str(e)}")

        return self._exchange

    async def close(self):
        """关闭连接"""
        if self._exchange:
            await self._exchange.close()
            self._exchange = None
            logger.info("Exchange connection closed")

    # ==================== 市场数据相关 ====================

    @api_call(max_retries=3, timeout=10.0)
    async def fetch_ticker(self, symbol: str) -> Dict[str, Any]:
        """
        获取最新价格

        Args:
            symbol: 交易对符号，如 'BTC/USDT'

        Returns:
            Dict包含价格信息：
            {
                'symbol': 'BTC/USDT',
                'last': 50000.0,
                'bid': 49999.0,
                'ask': 50001.0,
                'high': 51000.0,
                'low': 49000.0,
                'volume': 1000.0,
                ...
            }
        """
        # 限流
        limiter = self._rate_limiters.get_limiter(self._exchange_name)
        await limiter.acquire()

        exchange = await self._get_exchange()
        return await exchange.fetch_ticker(symbol)

    @api_call(max_retries=3, timeout=15.0)
    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = '1h',
        since: Optional[int] = None,
        limit: int = 100
    ) -> List[List]:
        """
        获取K线数据

        Args:
            symbol: 交易对符号
            timeframe: 时间周期，如 '1m', '5m', '1h', '1d'
            since: 起始时间戳（毫秒）
            limit: 返回数量

        Returns:
            List of [timestamp, open, high, low, close, volume]
        """
        # 限流
        limiter = self._rate_limiters.get_limiter(self._exchange_name)
        await limiter.acquire()

        exchange = await self._get_exchange()
        return await exchange.fetch_ohlcv(symbol, timeframe, since, limit)

    @api_call(max_retries=3, timeout=10.0)
    async def fetch_order_book(
        self,
        symbol: str,
        limit: int = 20
    ) -> Dict[str, Any]:
        """
        获取订单簿

        Args:
            symbol: 交易对符号
            limit: 深度限制

        Returns:
            Dict包含买卖盘：
            {
                'bids': [[price, amount], ...],
                'asks': [[price, amount], ...],
                'timestamp': 1234567890,
                ...
            }
        """
        # 限流
        limiter = self._rate_limiters.get_limiter(self._exchange_name)
        await limiter.acquire()

        exchange = await self._get_exchange()
        return await exchange.fetch_order_book(symbol, limit)

    @cached(ttl=60)  # 缓存60秒
    @api_call(max_retries=2, timeout=5.0)
    async def fetch_markets(self) -> List[Dict]:
        """
        获取所有市场信息

        Returns:
            List of market info dicts
        """
        exchange = await self._get_exchange()
        return list(exchange.markets.values())

    @api_call(max_retries=2, timeout=5.0)
    async def fetch_status(self) -> Dict[str, Any]:
        """
        获取交易所状态

        Returns:
            Dict包含交易所状态信息
        """
        limiter = self._rate_limiters.get_limiter(self._exchange_name)
        await limiter.acquire()

        exchange = await self._get_exchange()
        return await exchange.fetch_status()

    # ==================== 账户相关 ====================

    @api_call(max_retries=3, timeout=10.0)
    async def fetch_balance(self) -> Dict[str, Any]:
        """
        获取账户余额

        Returns:
            Dict包含所有币种余额：
            {
                'USDT': {'free': 1000.0, 'used': 100.0, 'total': 1100.0},
                'BTC': {...},
                ...
            }
        """
        limiter = self._rate_limiters.get_limiter(self._exchange_name)
        await limiter.acquire()

        exchange = await self._get_exchange()
        return await exchange.fetch_balance()

    @api_call(max_retries=3, timeout=10.0)
    async def fetch_positions(self, symbols: Optional[List[str]] = None) -> List[Dict]:
        """
        获取持仓信息

        Args:
            symbols: 可选，指定交易对列表

        Returns:
            List of position dicts
        """
        limiter = self._rate_limiters.get_limiter(self._exchange_name)
        await limiter.acquire()

        exchange = await self._get_exchange()
        return await exchange.fetch_positions(symbols)

    @api_call(max_retries=2, timeout=10.0)
    async def fetch_my_trades(
        self,
        symbol: str,
        since: Optional[int] = None,
        limit: Optional[int] = None
    ) -> List[Dict]:
        """
        获取我的成交记录

        Args:
            symbol: 交易对符号
            since: 起始时间戳 (毫秒)
            limit: 返回数量限制

        Returns:
            成交记录列表
        """
        limiter = self._rate_limiters.get_limiter(self._exchange_name)
        await limiter.acquire()

        exchange = await self._get_exchange()
        return await exchange.fetch_my_trades(symbol, since, limit)

    # ==================== 杠杆和保证金相关 ====================

    @api_call(max_retries=2, timeout=10.0)
    async def set_leverage(self, leverage: int, symbol: str) -> Dict[str, Any]:
        """
        设置交易对杠杆倍数

        Args:
            leverage: 杠杆倍数 (1-125)
            symbol: 交易对符号

        Returns:
            Dict包含杠杆设置结果
        """
        limiter = self._rate_limiters.get_limiter(self._exchange_name)
        await limiter.acquire()

        exchange = await self._get_exchange()

        logger.info(f"Setting leverage for {symbol}: {leverage}x")

        return await exchange.set_leverage(leverage, symbol)

    # ==================== 订单相关 ====================

    @api_call(max_retries=2, timeout=15.0)
    async def create_order(
        self,
        symbol: str,
        order_type: str,
        side: str,
        amount: float,
        price: Optional[float] = None,
        params: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        创建订单

        Args:
            symbol: 交易对符号
            order_type: 订单类型 'market' or 'limit'
            side: 'buy' or 'sell'
            amount: 数量
            price: 价格（限价单必需）
            params: 额外参数（如杠杆等）

        Returns:
            Dict包含订单信息
        """
        limiter = self._rate_limiters.get_limiter(self._exchange_name)
        await limiter.acquire()

        exchange = await self._get_exchange()

        logger.info(
            f"Creating {side} {order_type} order: {symbol} "
            f"amount={amount} price={price}"
        )

        return await exchange.create_order(
            symbol, order_type, side, amount, price, params
        )

    @api_call(max_retries=3, timeout=10.0)
    async def cancel_order(self, order_id: str, symbol: str) -> Dict[str, Any]:
        """
        取消订单

        Args:
            order_id: 订单ID
            symbol: 交易对符号

        Returns:
            Dict包含取消结果
        """
        limiter = self._rate_limiters.get_limiter(self._exchange_name)
        await limiter.acquire()

        exchange = await self._get_exchange()

        logger.info(f"Cancelling order: {order_id} for {symbol}")

        return await exchange.cancel_order(order_id, symbol)

    @api_call(max_retries=3, timeout=10.0)
    async def fetch_order(self, order_id: str, symbol: str) -> Dict[str, Any]:
        """
        查询订单状态

        Args:
            order_id: 订单ID
            symbol: 交易对符号

        Returns:
            Dict包含订单详情
        """
        limiter = self._rate_limiters.get_limiter(self._exchange_name)
        await limiter.acquire()

        exchange = await self._get_exchange()
        return await exchange.fetch_order(order_id, symbol)

    @api_call(max_retries=3, timeout=10.0)
    async def fetch_open_orders(
        self,
        symbol: Optional[str] = None
    ) -> List[Dict]:
        """
        获取未完成订单

        Args:
            symbol: 可选，指定交易对

        Returns:
            List of order dicts
        """
        limiter = self._rate_limiters.get_limiter(self._exchange_name)
        await limiter.acquire()

        exchange = await self._get_exchange()
        return await exchange.fetch_open_orders(symbol)

    @api_call(max_retries=3, timeout=10.0)
    async def fetch_order_trades(
        self,
        order_id: str,
        symbol: str
    ) -> List[Dict]:
        """
        获取订单成交记录

        Args:
            order_id: 订单ID
            symbol: 交易对符号

        Returns:
            List of trade dicts
        """
        limiter = self._rate_limiters.get_limiter(self._exchange_name)
        await limiter.acquire()

        exchange = await self._get_exchange()

        # 有些交易所可能不支持这个方法
        if hasattr(exchange, 'fetch_order_trades'):
            return await exchange.fetch_order_trades(order_id, symbol)
        else:
            logger.warning(f"{self._exchange_name} doesn't support fetch_order_trades")
            return []

    # ==================== 工具方法 ====================

    def get_rate_limiter_stats(self) -> Dict[str, Any]:
        """获取限流器统计信息"""
        return self._rate_limiters.get_all_stats()

    async def health_check(self) -> bool:
        """
        健康检查

        Returns:
            True if healthy, False otherwise
        """
        try:
            await self.fetch_status()
            return True
        except Exception as e:
            logger.error(f"Health check failed: {str(e)}")
            return False


# 全局单例实例
_exchange_service: Optional[ExchangeService] = None


def get_exchange_service() -> ExchangeService:
    """
    获取全局ExchangeService单例

    Returns:
        ExchangeService实例
    """
    global _exchange_service
    if _exchange_service is None:
        _exchange_service = ExchangeService()
    return _exchange_service


async def close_exchange_service() -> None:
    """关闭全局 ExchangeService 实例"""
    global _exchange_service
    if _exchange_service is not None:
        try:
            await _exchange_service.close()
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("关闭 ExchangeService 失败: %s", exc)
        finally:
            _exchange_service = None
