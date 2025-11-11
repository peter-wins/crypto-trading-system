"""
Macro Economic Data Collector

采集宏观经济数据:
- 美联储利率
- CPI/失业率等经济指标
- 美元指数 (DXY)
- 黄金/原油价格
"""

import asyncio
from datetime import datetime, timezone
from typing import Optional

from src.core.logger import get_logger
from src.models.environment import MacroData
from src.perception.http_utils import get_http_client

logger = get_logger(__name__)


class MacroCollector:
    """宏观经济数据采集器"""

    def __init__(self):
        self.http_client = get_http_client()

    async def close(self):
        """关闭资源（HTTP 客户端由全局管理，这里不需要关闭）"""
        pass

    async def get_dxy_index(self) -> Optional[dict]:
        """
        获取美元指数 (DXY)

        数据源: Yahoo Finance API (免费)
        """
        try:
            # Yahoo Finance 使用 DX-Y.NYB 代码表示美元指数期货
            symbol = "DX-Y.NYB"
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
            params = {
                "interval": "1d",
                "range": "5d",
            }

            data = await self.http_client.get_json(url, params=params)

            if data and "chart" in data and "result" in data["chart"]:
                result = data["chart"]["result"][0]
                meta = result.get("meta", {})

                current_price = meta.get("regularMarketPrice")
                previous_close = meta.get("previousClose")

                if current_price and previous_close:
                    change_24h = ((current_price - previous_close) / previous_close) * 100

                    logger.debug(
                        f"美元指数: {current_price:.2f} ({change_24h:+.2f}%)"
                    )

                    return {
                        "value": current_price,
                        "change_24h": change_24h,
                    }

            logger.warning("美元指数数据解析失败或无效")
            return None

        except Exception as e:
            logger.error(f"美元指数获取异常: {e}")
            return None

    async def get_gold_price(self) -> Optional[float]:
        """
        获取黄金价格 (USD/oz)

        数据源: Yahoo Finance API
        """
        try:
            # GC=F 是黄金期货代码
            symbol = "GC=F"
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
            params = {
                "interval": "1d",
                "range": "1d",
            }

            data = await self.http_client.get_json(url, params=params)

            if data and "chart" in data and "result" in data["chart"]:
                result = data["chart"]["result"][0]
                meta = result.get("meta", {})
                current_price = meta.get("regularMarketPrice")

                if current_price:
                    logger.debug(f"黄金价格: ${current_price:.2f}/oz")
                    return float(current_price)

            logger.warning("黄金价格数据解析失败或无效")
            return None

        except Exception as e:
            logger.error(f"黄金价格获取异常: {e}")
            return None

    async def get_oil_price(self) -> Optional[float]:
        """
        获取原油价格 (USD/barrel)

        数据源: Yahoo Finance API (WTI 原油期货)
        """
        try:
            # CL=F 是 WTI 原油期货代码
            symbol = "CL=F"
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
            params = {
                "interval": "1d",
                "range": "1d",
            }

            data = await self.http_client.get_json(url, params=params)

            if data and "chart" in data and "result" in data["chart"]:
                result = data["chart"]["result"][0]
                meta = result.get("meta", {})
                current_price = meta.get("regularMarketPrice")

                if current_price:
                    logger.debug(f"原油价格: ${current_price:.2f}/barrel")
                    return float(current_price)

            logger.warning("原油价格数据解析失败或无效")
            return None

        except Exception as e:
            logger.error(f"原油价格获取异常: {e}")
            return None

    async def get_fed_rate(self) -> Optional[dict]:
        """
        获取联邦基金利率

        注意: 这个数据更新频率低,可以缓存更长时间
        数据源: FRED API (需要 API key) 或使用静态配置

        暂时禁用，避免模拟数据影响决策
        """
        # TODO: 集成真实的美联储利率 API
        # 目前返回 None，不使用模拟数据
        logger.debug("美联储利率: 暂未集成真实数据源，跳过")
        return None

    async def get_economic_indicators(self) -> Optional[dict]:
        """
        获取经济指标 (CPI, 失业率等)

        注意: 这些数据更新频率很低 (月度),建议缓存
        数据源: FRED API 或其他经济数据 API

        暂时禁用，避免模拟数据影响决策
        """
        # TODO: 集成真实的经济指标 API
        logger.debug("经济指标: 暂未集成真实数据源，跳过")
        return None

    async def get_macro_data(self) -> MacroData:
        """
        获取完整的宏观经济数据

        顺序采集（HTTP 客户端内部会处理延迟和缓存）
        """
        logger.info("开始采集宏观经济数据...")

        # 顺序采集所有数据（HTTP 客户端会自动处理延迟避免 429）
        fed_rate_data = await self.get_fed_rate()
        economic_data = await self.get_economic_indicators()

        # 注释掉频繁失败的 Yahoo Finance 数据源 (HTTP 429)
        # dxy_data = await self.get_dxy_index()
        # gold_price = await self.get_gold_price()
        # oil_price = await self.get_oil_price()
        dxy_data = None
        gold_price = None
        oil_price = None
        logger.debug("Yahoo Finance 数据源已禁用 (频繁 HTTP 429)")

        # 构建宏观数据
        macro = MacroData(
            fed_rate=fed_rate_data.get("rate") if isinstance(fed_rate_data, dict) else None,
            fed_rate_trend=fed_rate_data.get("trend") if isinstance(fed_rate_data, dict) else None,
            cpi=economic_data.get("cpi") if isinstance(economic_data, dict) else None,
            unemployment=economic_data.get("unemployment") if isinstance(economic_data, dict) else None,
            dxy=dxy_data.get("value") if isinstance(dxy_data, dict) else None,
            dxy_change_24h=dxy_data.get("change_24h") if isinstance(dxy_data, dict) else None,
            gold_price=gold_price if not isinstance(gold_price, Exception) else None,
            oil_price=oil_price if not isinstance(oil_price, Exception) else None,
            updated_at=datetime.now(timezone.utc),
        )

        logger.info("宏观经济数据采集完成 (仅使用可用数据源)")
        return macro


# 测试代码
async def main():
    """测试宏观数据采集"""
    collector = MacroCollector()

    try:
        macro = await collector.get_macro_data()

        print("\n=== 宏观经济数据 ===")
        print(f"美联储利率: {macro.fed_rate}% ({macro.fed_rate_trend})")
        print(f"CPI 通胀率: {macro.cpi}%")
        print(f"失业率: {macro.unemployment}%")
        if macro.dxy is not None and macro.dxy_change_24h is not None:
            print(f"美元指数: {macro.dxy} ({macro.dxy_change_24h:+.2f}%)")
        else:
            print(f"美元指数: 暂无数据")
        print(f"黄金价格: ${macro.gold_price}/oz" if macro.gold_price else "黄金价格: 暂无数据")
        print(f"原油价格: ${macro.oil_price}/barrel" if macro.oil_price else "原油价格: 暂无数据")

    finally:
        await collector.close()


if __name__ == "__main__":
    asyncio.run(main())
