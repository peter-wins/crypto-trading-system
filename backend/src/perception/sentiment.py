"""
Market Sentiment Data Collector

采集市场情绪数据:
- 恐慌贪婪指数 (Fear & Greed Index)
- 资金费率 (Funding Rate)
- 多空比 (Long/Short Ratio)
"""

import asyncio
from datetime import datetime, timezone
from typing import Optional

import aiohttp

from src.core.logger import get_logger
from src.models.environment import SentimentData

logger = get_logger(__name__)


class SentimentCollector:
    """市场情绪数据采集器"""

    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None

    async def _ensure_session(self):
        """确保 HTTP session 存在"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()

    async def close(self):
        """关闭 HTTP session"""
        if self.session and not self.session.closed:
            await self.session.close()

    async def get_fear_greed_index(self) -> Optional[dict]:
        """
        获取恐慌贪婪指数

        数据源: Alternative.me API
        URL: https://api.alternative.me/fng/
        免费,无需 API key
        """
        await self._ensure_session()

        try:
            url = "https://api.alternative.me/fng/?limit=1"
            async with self.session.get(url, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("data") and len(data["data"]) > 0:
                        latest = data["data"][0]
                        value = int(latest["value"])
                        classification = latest["value_classification"]

                        logger.info(
                            f"恐慌贪婪指数: {value} ({classification})"
                        )

                        return {
                            "value": value,
                            "classification": classification.lower(),
                        }
                else:
                    logger.warning(
                        f"恐慌贪婪指数获取失败: HTTP {response.status}"
                    )
                    return None

        except Exception as e:
            logger.error(f"恐慌贪婪指数获取异常: {e}")
            return None

    async def get_funding_rate(self, symbol: str = "BTC") -> Optional[float]:
        """
        获取资金费率

        数据源: Binance API
        正数表示多头付费给空头 (市场看多)
        负数表示空头付费给多头 (市场看空)

        Args:
            symbol: 币种符号,如 BTC, ETH
        """
        await self._ensure_session()

        try:
            # Binance 永续合约的 symbol 格式: BTCUSDT
            binance_symbol = f"{symbol}USDT"
            url = f"https://fapi.binance.com/fapi/v1/premiumIndex?symbol={binance_symbol}"

            async with self.session.get(url, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    # 资金费率是小数,转换为百分比
                    funding_rate = float(data["lastFundingRate"]) * 100

                    logger.debug(
                        f"{symbol} 资金费率: {funding_rate:.4f}%"
                    )

                    return funding_rate
                else:
                    logger.warning(
                        f"{symbol} 资金费率获取失败: HTTP {response.status}"
                    )
                    return None

        except Exception as e:
            logger.error(f"{symbol} 资金费率获取异常: {e}")
            return None

    async def get_long_short_ratio(self, symbol: str = "BTC") -> Optional[float]:
        """
        获取多空比

        数据源: Binance API
        > 1 表示多头占优
        < 1 表示空头占优

        Args:
            symbol: 币种符号
        """
        await self._ensure_session()

        try:
            binance_symbol = f"{symbol}USDT"
            url = (
                f"https://fapi.binance.com/futures/data/globalLongShortAccountRatio"
                f"?symbol={binance_symbol}&period=5m&limit=1"
            )

            async with self.session.get(url, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    if data and len(data) > 0:
                        ratio = float(data[0]["longShortRatio"])

                        logger.debug(
                            f"{symbol} 多空比: {ratio:.2f}"
                        )

                        return ratio
                else:
                    logger.warning(
                        f"{symbol} 多空比获取失败: HTTP {response.status}"
                    )
                    return None

        except Exception as e:
            logger.error(f"{symbol} 多空比获取异常: {e}")
            return None

    async def get_sentiment_data(self) -> SentimentData:
        """
        获取完整的市场情绪数据

        并行采集所有情绪指标
        """
        logger.info("开始采集市场情绪数据...")

        # 并行采集所有数据
        results = await asyncio.gather(
            self.get_fear_greed_index(),
            self.get_funding_rate("BTC"),
            self.get_funding_rate("ETH"),
            self.get_long_short_ratio("BTC"),
            self.get_long_short_ratio("ETH"),
            return_exceptions=True,
        )

        # 解包结果
        fear_greed, btc_funding, eth_funding, btc_ratio, eth_ratio = results

        # 处理恐慌贪婪指数
        fear_greed_index = None
        fear_greed_label = None
        if isinstance(fear_greed, dict):
            fear_greed_index = fear_greed["value"]
            fear_greed_label = fear_greed["classification"]

        # 构建情绪数据
        sentiment = SentimentData(
            fear_greed_index=fear_greed_index,
            fear_greed_label=fear_greed_label,
            btc_funding_rate=btc_funding if not isinstance(btc_funding, Exception) else None,
            eth_funding_rate=eth_funding if not isinstance(eth_funding, Exception) else None,
            btc_long_short_ratio=btc_ratio if not isinstance(btc_ratio, Exception) else None,
            eth_long_short_ratio=eth_ratio if not isinstance(eth_ratio, Exception) else None,
            updated_at=datetime.now(timezone.utc),
        )

        logger.info(
            f"情绪数据采集完成: {sentiment.get_overall_sentiment()} "
            f"(恐慌贪婪指数: {fear_greed_index})"
        )

        return sentiment


# 测试代码
async def main():
    """测试情绪数据采集"""
    collector = SentimentCollector()

    try:
        sentiment = await collector.get_sentiment_data()
        print("\n=== 市场情绪数据 ===")
        print(f"恐慌贪婪指数: {sentiment.fear_greed_index} ({sentiment.fear_greed_label})")
        print(f"综合情绪: {sentiment.get_overall_sentiment()}")
        print(f"BTC 资金费率: {sentiment.btc_funding_rate}%")
        print(f"ETH 资金费率: {sentiment.eth_funding_rate}%")
        print(f"BTC 多空比: {sentiment.btc_long_short_ratio}")
        print(f"ETH 多空比: {sentiment.eth_long_short_ratio}")

    finally:
        await collector.close()


if __name__ == "__main__":
    asyncio.run(main())
