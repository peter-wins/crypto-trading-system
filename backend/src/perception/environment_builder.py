"""
Market Environment Builder

汇总感知层所有数据源,构建完整的 MarketEnvironment
"""

import asyncio
from datetime import datetime, timezone
from typing import Optional

from src.core.logger import get_logger
from src.models.environment import MarketEnvironment
from src.perception.sentiment import SentimentCollector
from src.perception.macro import MacroCollector
from src.perception.stocks import StockCollector
from src.perception.crypto_overview import CryptoOverviewCollector
from src.perception.news import NewsCollector

logger = get_logger(__name__)


class EnvironmentBuilder:
    """市场环境构建器"""

    def __init__(
        self,
        llm_client=None,
        cryptopanic_api_key: Optional[str] = None,
        enable_news: bool = False,
    ):
        """
        初始化环境构建器

        Args:
            llm_client: LLM 客户端(用于新闻分析)
            cryptopanic_api_key: CryptoPanic API Key
            enable_news: 是否启用新闻采集(较慢,可选)
        """
        self.sentiment_collector = SentimentCollector()
        self.macro_collector = MacroCollector()
        self.stock_collector = StockCollector()
        self.crypto_collector = CryptoOverviewCollector()
        self.news_collector = NewsCollector(
            llm_client=llm_client,
            cryptopanic_api_key=cryptopanic_api_key,
        ) if enable_news else None

    async def close(self):
        """关闭所有采集器"""
        await self.sentiment_collector.close()
        await self.macro_collector.close()
        await self.stock_collector.close()
        await self.crypto_collector.close()
        if self.news_collector:
            await self.news_collector.close()

    async def build_environment(self) -> MarketEnvironment:
        """
        构建完整的市场环境数据

        并行采集所有数据源,构建 MarketEnvironment 对象
        失败的数据源会被标记为 None,不影响整体流程
        """
        import time
        logger.info("开始构建市场环境...")

        # 并行采集所有数据(新闻除外,因为较慢) - 每个任务都有15秒超时
        async def fetch_with_timeout_and_log(name, coro, timeout=15.0):
            """带超时和日志的数据获取"""
            t1 = time.time()
            try:
                result = await asyncio.wait_for(coro, timeout=timeout)
                t2 = time.time()
                logger.info(f"[环境数据] {name} 获取成功，耗时: {t2-t1:.2f}秒")
                return result
            except asyncio.TimeoutError:
                t2 = time.time()
                logger.warning(f"[环境数据] {name} 获取超时（{timeout}秒），跳过")
                return None
            except Exception as e:
                t2 = time.time()
                logger.warning(f"[环境数据] {name} 获取失败（{t2-t1:.2f}秒）: {str(e)[:100]}")
                return None

        tasks = [
            fetch_with_timeout_and_log("情绪数据", self.sentiment_collector.get_sentiment_data()),
            fetch_with_timeout_and_log("宏观数据", self.macro_collector.get_macro_data()),
            fetch_with_timeout_and_log("美股数据", self.stock_collector.get_stock_market_data()),
            fetch_with_timeout_and_log("加密概览", self.crypto_collector.get_market_overview()),
        ]

        results = await asyncio.gather(*tasks)

        # 解包结果
        sentiment = results[0]
        macro = results[1]
        stock_market = results[2]
        crypto_overview = results[3]

        # 获取新闻(如果启用)
        recent_news = []
        if self.news_collector:
            try:
                recent_news = await self.news_collector.get_recent_news(
                    hours=24,
                    limit=10,
                    use_llm=self.news_collector.llm_client is not None,  # 只有配置了 LLM 才分析
                    use_rss=True,  # 优先使用 RSS (免费)
                )
            except Exception as e:
                logger.error(f"新闻采集失败: {e}")

        # 构建环境对象
        now = datetime.now(timezone.utc)
        environment = MarketEnvironment(
            timestamp=int(now.timestamp() * 1000),
            dt=now,
            # 外部数据
            sentiment=sentiment,
            macro=macro,
            stock_market=stock_market,
            recent_news=recent_news,
            # 加密市场概览
            crypto_market_cap=crypto_overview.get("total_market_cap") if crypto_overview else None,
            crypto_market_cap_change_24h=crypto_overview.get("market_cap_change_24h") if crypto_overview else None,
            btc_dominance=crypto_overview.get("btc_dominance") if crypto_overview else None,
            total_volume_24h=crypto_overview.get("total_volume_24h") if crypto_overview else None,
        )

        # 计算数据完整度
        environment.calculate_data_completeness()

        logger.info(
            f"市场环境构建完成: {environment.get_summary()} "
            f"(数据完整度: {environment.data_completeness:.0%})"
        )

        return environment


# 测试代码
async def main():
    """测试环境构建器"""
    builder = EnvironmentBuilder()

    try:
        environment = await builder.build_environment()

        print("\n" + "=" * 60)
        print("市场环境数据")
        print("=" * 60)
        print(f"时间: {environment.dt}")
        print(f"数据完整度: {environment.data_completeness:.0%}")
        print(f"摘要: {environment.get_summary()}")

        if environment.macro:
            print("\n--- 宏观经济 ---")
            print(f"美联储利率: {environment.macro.fed_rate}% ({environment.macro.fed_rate_trend})")
            print(f"CPI: {environment.macro.cpi}%")
            print(f"失业率: {environment.macro.unemployment}%")
            if environment.macro.dxy:
                print(f"美元指数: {environment.macro.dxy:.2f} ({environment.macro.dxy_change_24h:+.2f}%)")
            if environment.macro.gold_price:
                print(f"黄金: ${environment.macro.gold_price:.2f}/oz")
            if environment.macro.oil_price:
                print(f"原油: ${environment.macro.oil_price:.2f}/barrel")

        if environment.stock_market:
            print("\n--- 美股市场 ---")
            if environment.stock_market.sp500:
                print(f"标普500: {environment.stock_market.sp500:.2f} ({environment.stock_market.sp500_change_24h:+.2f}%)")
            if environment.stock_market.nasdaq:
                print(f"纳斯达克: {environment.stock_market.nasdaq:.2f} ({environment.stock_market.nasdaq_change_24h:+.2f}%)")
            if environment.stock_market.coin_stock:
                print(f"COIN: ${environment.stock_market.coin_stock:.2f} ({environment.stock_market.coin_change_24h:+.2f}%)")
            if environment.stock_market.mstr_stock:
                print(f"MSTR: ${environment.stock_market.mstr_stock:.2f} ({environment.stock_market.mstr_change_24h:+.2f}%)")

        if environment.sentiment:
            print("\n--- 市场情绪 ---")
            print(f"恐慌贪婪指数: {environment.sentiment.fear_greed_index} ({environment.sentiment.fear_greed_label})")
            print(f"综合情绪: {environment.sentiment.get_overall_sentiment()}")
            print(f"BTC 资金费率: {environment.sentiment.btc_funding_rate:.4f}%")
            print(f"ETH 资金费率: {environment.sentiment.eth_funding_rate:.4f}%")
            print(f"BTC 多空比: {environment.sentiment.btc_long_short_ratio:.2f}")
            print(f"ETH 多空比: {environment.sentiment.eth_long_short_ratio:.2f}")

        if environment.crypto_market_cap:
            print("\n--- 加密市场 ---")
            print(f"总市值: ${float(environment.crypto_market_cap)/1e12:.2f}T")
            print(f"市值变化: {environment.crypto_market_cap_change_24h:+.2f}%")
            print(f"BTC占比: {environment.btc_dominance:.1f}%")
            print(f"24h交易量: ${float(environment.total_volume_24h)/1e9:.2f}B")

        if environment.recent_news:
            print(f"\n--- 重大新闻 ({len(environment.recent_news)}条) ---")
            for news in environment.recent_news[:3]:
                print(f"[{news.impact_level}] {news.title}")
                print(f"  {news.source} | {news.sentiment}")

        print(f"\n是否可用于分析: {environment.is_ready_for_analysis()}")

    finally:
        await builder.close()


if __name__ == "__main__":
    asyncio.run(main())
