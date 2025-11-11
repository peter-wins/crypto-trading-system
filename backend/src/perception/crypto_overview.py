"""
Crypto Market Overview Collector

采集加密货币市场概览数据:
- 总市值
- BTC 市值占比
- 24h 交易量
"""

import asyncio
from decimal import Decimal
from typing import Optional

import aiohttp

from src.core.logger import get_logger

logger = get_logger(__name__)


class CryptoOverviewCollector:
    """加密市场概览数据采集器"""

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

    async def get_market_overview(self) -> Optional[dict]:
        """
        获取加密市场概览

        数据源: CoinGecko API (免费,无需 API key)
        """
        await self._ensure_session()

        try:
            url = "https://api.coingecko.com/api/v3/global"

            async with self.session.get(url, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()

                    if "data" in data:
                        global_data = data["data"]

                        total_market_cap_usd = global_data.get("total_market_cap", {}).get("usd")
                        total_volume_24h_usd = global_data.get("total_volume", {}).get("usd")
                        market_cap_change_24h = global_data.get("market_cap_change_percentage_24h_usd")
                        btc_dominance = global_data.get("market_cap_percentage", {}).get("btc")

                        logger.info(
                            f"加密市场: 总市值 ${total_market_cap_usd/1e12:.2f}T, "
                            f"BTC占比 {btc_dominance:.1f}%"
                        )

                        return {
                            "total_market_cap": Decimal(str(total_market_cap_usd)) if total_market_cap_usd else None,
                            "total_volume_24h": Decimal(str(total_volume_24h_usd)) if total_volume_24h_usd else None,
                            "market_cap_change_24h": float(market_cap_change_24h) if market_cap_change_24h else None,
                            "btc_dominance": float(btc_dominance) if btc_dominance else None,
                        }
                else:
                    logger.warning(f"加密市场概览获取失败: HTTP {response.status}")
                    return None

        except Exception as e:
            logger.error(f"加密市场概览获取异常: {e}")
            return None


# 测试代码
async def main():
    """测试加密市场概览采集"""
    collector = CryptoOverviewCollector()

    try:
        overview = await collector.get_market_overview()

        if overview:
            print("\n=== 加密市场概览 ===")
            if overview["total_market_cap"]:
                print(f"总市值: ${float(overview['total_market_cap'])/1e12:.2f}T")
            if overview["market_cap_change_24h"]:
                print(f"市值24h变化: {overview['market_cap_change_24h']:+.2f}%")
            if overview["btc_dominance"]:
                print(f"BTC市值占比: {overview['btc_dominance']:.1f}%")
            if overview["total_volume_24h"]:
                print(f"24h总交易量: ${float(overview['total_volume_24h'])/1e9:.2f}B")
        else:
            print("加密市场概览: 暂无数据")

    finally:
        await collector.close()


if __name__ == "__main__":
    asyncio.run(main())
