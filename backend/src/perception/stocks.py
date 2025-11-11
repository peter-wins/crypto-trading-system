"""
Stock Market Data Collector

采集美股市场数据:
- 标普500 (S&P 500)
- 纳斯达克 (NASDAQ)
- 加密相关股票 (COIN, MSTR)
"""

import asyncio
from datetime import datetime, timezone
from typing import Optional

from src.core.logger import get_logger
from src.models.environment import StockMarketData
from src.perception.http_utils import get_http_client

logger = get_logger(__name__)


class StockCollector:
    """美股市场数据采集器"""

    def __init__(self):
        self.http_client = get_http_client()

    async def close(self):
        """关闭资源（HTTP 客户端由全局管理，这里不需要关闭）"""
        pass

    async def get_stock_data(self, symbol: str) -> Optional[dict]:
        """
        获取股票数据

        数据源: Yahoo Finance API
        Args:
            symbol: 股票代码,如 ^GSPC (S&P 500), ^IXIC (NASDAQ), COIN, MSTR
        """
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
            params = {
                "interval": "1d",
                "range": "5d",
            }

            # 使用带缓存和重试的 HTTP 客户端
            data = await self.http_client.get_json(url, params=params)

            if data and "chart" in data and "result" in data["chart"]:
                result = data["chart"]["result"][0]
                meta = result.get("meta", {})

                current_price = meta.get("regularMarketPrice")
                previous_close = meta.get("previousClose")

                if current_price and previous_close:
                    change_24h = ((current_price - previous_close) / previous_close) * 100

                    logger.debug(
                        f"{symbol}: {current_price:.2f} ({change_24h:+.2f}%)"
                    )

                    return {
                        "price": current_price,
                        "change_24h": change_24h,
                    }

            logger.warning(f"{symbol} 数据解析失败或无效")
            return None

        except Exception as e:
            logger.error(f"{symbol} 数据获取异常: {e}")
            return None

    async def get_stock_market_data(self) -> StockMarketData:
        """
        获取完整的美股市场数据

        暂时禁用，避免 Yahoo Finance HTTP 429 影响决策
        """
        logger.info("美股市场数据采集已禁用 (Yahoo Finance 频繁 HTTP 429)")

        # 注释掉频繁失败的 Yahoo Finance 数据源 (HTTP 429)
        # sp500_data = await self.get_stock_data("^GSPC")  # S&P 500
        # nasdaq_data = await self.get_stock_data("^IXIC")  # NASDAQ
        # coin_data = await self.get_stock_data("COIN")   # Coinbase
        # mstr_data = await self.get_stock_data("MSTR")   # MicroStrategy

        # 返回空数据
        stock_market = StockMarketData(
            sp500=None,
            sp500_change_24h=None,
            nasdaq=None,
            nasdaq_change_24h=None,
            coin_stock=None,
            coin_change_24h=None,
            mstr_stock=None,
            mstr_change_24h=None,
            correlation_with_crypto=None,
            updated_at=datetime.now(timezone.utc),
        )

        logger.info("美股市场数据采集完成 (跳过)")
        return stock_market


# 测试代码
async def main():
    """测试美股数据采集"""
    collector = StockCollector()

    try:
        stock_market = await collector.get_stock_market_data()

        print("\n=== 美股市场数据 ===")

        if stock_market.sp500 is not None:
            print(f"标普500: {stock_market.sp500:.2f} ({stock_market.sp500_change_24h:+.2f}%)")
        else:
            print("标普500: 暂无数据")

        if stock_market.nasdaq is not None:
            print(f"纳斯达克: {stock_market.nasdaq:.2f} ({stock_market.nasdaq_change_24h:+.2f}%)")
        else:
            print("纳斯达克: 暂无数据")

        if stock_market.coin_stock is not None:
            print(f"COIN 股价: ${stock_market.coin_stock:.2f} ({stock_market.coin_change_24h:+.2f}%)")
        else:
            print("COIN: 暂无数据")

        if stock_market.mstr_stock is not None:
            print(f"MSTR 股价: ${stock_market.mstr_stock:.2f} ({stock_market.mstr_change_24h:+.2f}%)")
        else:
            print("MSTR: 暂无数据")

    finally:
        await collector.close()


if __name__ == "__main__":
    asyncio.run(main())
