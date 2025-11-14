"""
News Event Collector

采集并分析加密货币新闻事件:
1. 从 RSS feed 或新闻 API 获取最新新闻
2. 使用 LLM 分析新闻的影响级别和情绪
"""

import asyncio
from datetime import datetime, timezone, timedelta
from typing import List, Optional
import json
import re
from html import unescape
from email.utils import parsedate_to_datetime
import xml.etree.ElementTree as ET

import aiohttp

from src.core.logger import get_logger
from src.models.environment import NewsEvent

logger = get_logger(__name__)

# RSS 新闻源列表
RSS_FEEDS = [
    "https://coinjournal.net/news/feed/",
    "https://cointelegraph.com/rss",
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
]


class NewsCollector:
    """
    新闻事件采集器

    数据源:
    1. RSS feeds (免费,无需 API key) - 推荐
    2. CryptoPanic API (免费,需要 API key)

    LLM 分析: 使用 DeepSeek 分析新闻影响和情绪
    """

    def __init__(self, llm_client=None, cryptopanic_api_key: Optional[str] = None):
        self.session: Optional[aiohttp.ClientSession] = None
        self.llm_client = llm_client
        self.cryptopanic_api_key = cryptopanic_api_key

    @staticmethod
    def _strip_html_tags(text: str) -> str:
        """移除 HTML 标签"""
        if not text:
            return ""
        cleaned = unescape(text)
        cleaned = re.sub(r"<[^>]+>", " ", cleaned)
        return re.sub(r"\s+", " ", cleaned).strip()

    async def _ensure_session(self):
        """确保 HTTP session 存在"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()

    async def close(self):
        """关闭 HTTP session"""
        if self.session and not self.session.closed:
            await self.session.close()

    async def fetch_news_from_rss(self, feed_url: str, limit: int = 10) -> List[dict]:
        """
        从 RSS feed 获取新闻

        Args:
            feed_url: RSS feed URL
            limit: 获取新闻数量

        Returns:
            新闻列表
        """
        await self._ensure_session()

        try:
            async with self.session.get(feed_url, timeout=15) as response:
                if response.status != 200:
                    logger.warning(f"RSS feed {feed_url} 请求失败: HTTP {response.status}")
                    return []

                content = await response.read()
                root = ET.fromstring(content)

                # 处理 RSS 2.0
                channel = root.find("channel")
                if channel is None:
                    # 尝试 Atom feed
                    namespace = {"atom": "http://www.w3.org/2005/Atom"}
                    entries = root.findall("atom:entry", namespace)
                    if not entries:
                        logger.warning(f"无法解析 RSS feed: {feed_url}")
                        return []
                    return await self._parse_atom_entries(entries, namespace, limit)

                # 解析 RSS 2.0
                news_list = []
                for item in channel.findall("item")[:limit]:
                    title = self._strip_html_tags(item.findtext("title") or "")
                    pub_date_raw = (item.findtext("pubDate") or "").strip()
                    summary_raw = item.findtext("description") or ""
                    link = item.findtext("link") or ""

                    summary = self._strip_html_tags(summary_raw)
                    # 清理常见的 footer 文本
                    summary = re.sub(
                        r"The post .*? appeared first on .*",
                        "",
                        summary,
                        flags=re.IGNORECASE
                    ).strip()

                    # 解析时间
                    published_at = None
                    if pub_date_raw:
                        try:
                            parsed = parsedate_to_datetime(pub_date_raw)
                            if parsed:
                                if parsed.tzinfo is None:
                                    parsed = parsed.replace(tzinfo=timezone.utc)
                                else:
                                    parsed = parsed.astimezone(timezone.utc)
                                published_at = parsed.isoformat()
                        except Exception as e:
                            logger.debug(f"时间解析失败: {e}")

                    if title:
                        # 从 URL 提取来源
                        source = "Unknown"
                        if "coinjournal" in feed_url:
                            source = "CoinJournal"
                        elif "cointelegraph" in feed_url:
                            source = "Cointelegraph"
                        elif "coindesk" in feed_url:
                            source = "CoinDesk"

                        news_list.append({
                            "title": title,
                            "summary": summary,
                            "url": link,
                            "source": source,
                            "published_at": published_at or datetime.now(timezone.utc).isoformat(),
                        })

                logger.info(f"从 {feed_url} 获取了 {len(news_list)} 条新闻")
                return news_list

        except Exception as e:
            logger.error(f"RSS feed {feed_url} 获取异常: {e}")
            return []

    async def _parse_atom_entries(self, entries, namespace, limit: int) -> List[dict]:
        """解析 Atom feed 条目"""
        news_list = []
        for entry in entries[:limit]:
            title_elem = entry.find("atom:title", namespace)
            title = self._strip_html_tags(title_elem.text if title_elem is not None else "")

            summary_elem = entry.find("atom:summary", namespace)
            summary = self._strip_html_tags(summary_elem.text if summary_elem is not None else "")

            link_elem = entry.find("atom:link", namespace)
            link = link_elem.get("href") if link_elem is not None else ""

            updated_elem = entry.find("atom:updated", namespace)
            published_at = updated_elem.text if updated_elem is not None else datetime.now(timezone.utc).isoformat()

            if title:
                news_list.append({
                    "title": title,
                    "summary": summary,
                    "url": link,
                    "source": "Atom Feed",
                    "published_at": published_at,
                })
        return news_list

    async def fetch_news_from_cryptopanic(self, limit: int = 20) -> List[dict]:
        """
        从 CryptoPanic 获取新闻

        Args:
            limit: 获取新闻数量

        Returns:
            新闻列表
        """
        await self._ensure_session()

        if not self.cryptopanic_api_key:
            logger.warning("未配置 CryptoPanic API Key,无法获取新闻")
            return []

        try:
            url = "https://cryptopanic.com/api/v1/posts/"
            params = {
                "auth_token": self.cryptopanic_api_key,
                "kind": "news",  # 只要新闻,不要社交媒体
                "filter": "important",  # 只要重要新闻
                "public": "true",
            }

            async with self.session.get(url, params=params, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    results = data.get("results", [])

                    news_list = []
                    for item in results[:limit]:
                        news_list.append({
                            "title": item.get("title", ""),
                            "url": item.get("url", ""),
                            "source": item.get("source", {}).get("title", "Unknown"),
                            "published_at": item.get("published_at", ""),
                        })

                    logger.info(f"从 CryptoPanic 获取了 {len(news_list)} 条新闻")
                    return news_list
                else:
                    logger.warning(f"CryptoPanic API 请求失败: HTTP {response.status}")
                    return []

        except Exception as e:
            logger.error(f"CryptoPanic 新闻获取异常: {e}")
            return []

    async def analyze_news_with_llm(self, news_item: dict) -> Optional[NewsEvent]:
        """
        使用 LLM 分析新闻的影响级别和情绪

        Args:
            news_item: 新闻条目

        Returns:
            NewsEvent 或 None
        """
        if not self.llm_client:
            # 没有 LLM,使用默认值
            return self._create_default_news_event(news_item)

        try:
            prompt = f"""
分析以下加密货币新闻,评估其影响级别和情绪。

新闻标题: {news_item['title']}
来源: {news_item['source']}

请输出 JSON 格式:
{{
    "impact_level": "low|medium|high|critical",
    "sentiment": "positive|neutral|negative",
    "related_symbols": ["BTC", "ETH"],
    "summary": "新闻摘要 (1-2句话)"
}}
"""

            from src.services.llm import Message

            messages = [
                Message(role="system", content="你是一个加密货币新闻分析专家。"),
                Message(role="user", content=prompt),
            ]

            response = await self.llm_client.chat(messages, tools=None, temperature=0.2, max_tokens=200)

            # 解析 LLM 响应
            try:
                result = json.loads(response.content or "{}")
            except json.JSONDecodeError:
                # 尝试提取 JSON
                import re
                json_match = re.search(r'\{[^{}]*\}', response.content or "")
                if json_match:
                    result = json.loads(json_match.group(0))
                else:
                    result = {}

            # 构建 NewsEvent
            published_at = news_item.get("published_at", "")
            try:
                dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
                timestamp = int(dt.timestamp() * 1000)
            except:
                dt = datetime.now(timezone.utc)
                timestamp = int(dt.timestamp() * 1000)

            return NewsEvent(
                timestamp=timestamp,
                dt=dt,
                title=news_item["title"],
                summary=result.get("summary", news_item["title"]),
                source=news_item["source"],
                impact_level=result.get("impact_level", "low"),
                sentiment=result.get("sentiment", "neutral"),
                related_symbols=result.get("related_symbols", []),
                url=news_item.get("url"),
            )

        except Exception as e:
            logger.error(f"LLM 分析新闻失败: {e}")
            return self._create_default_news_event(news_item)

    def _create_default_news_event(self, news_item: dict) -> NewsEvent:
        """创建默认的新闻事件(无 LLM 分析)"""
        published_at = news_item.get("published_at", "")
        try:
            dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
            timestamp = int(dt.timestamp() * 1000)
        except:
            dt = datetime.now(timezone.utc)
            timestamp = int(dt.timestamp() * 1000)

        return NewsEvent(
            timestamp=timestamp,
            dt=dt,
            title=news_item["title"],
            summary=news_item["title"],
            source=news_item["source"],
            impact_level="medium",  # 默认中等影响
            sentiment="neutral",  # 默认中性
            related_symbols=[],
            url=news_item.get("url"),
        )

    async def get_recent_news(
        self,
        hours: int = 24,
        limit: int = 10,
        use_llm: bool = True,
        use_rss: bool = True,
    ) -> List[NewsEvent]:
        """
        获取最近的重要新闻事件

        Args:
            hours: 获取最近多少小时的新闻
            limit: 最多获取多少条
            use_llm: 是否使用 LLM 分析
            use_rss: 是否使用 RSS feed (推荐,免费)

        Returns:
            新闻事件列表
        """
        logger.info(f"开始采集最近 {hours} 小时的新闻...")

        # 1. 获取原始新闻
        raw_news = []

        if use_rss:
            # 从多个 RSS feed 获取新闻
            for feed_url in RSS_FEEDS:
                try:
                    news = await self.fetch_news_from_rss(feed_url, limit=5)
                    raw_news.extend(news)
                except Exception as e:
                    logger.error(f"RSS feed {feed_url} 采集失败: {e}")
        elif self.cryptopanic_api_key:
            # 回退到 CryptoPanic API
            raw_news = await self.fetch_news_from_cryptopanic(limit=limit * 2)
        else:
            logger.warning("未配置 RSS 或 CryptoPanic API,无法获取新闻")
            return []

        if not raw_news:
            logger.warning("未获取到任何新闻")
            return []

        logger.info(f"原始新闻数量: {len(raw_news)}")

        # 2. 过滤时间范围
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
        filtered_news = []

        for item in raw_news:
            try:
                published_at = item.get("published_at", "")
                dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
                if dt >= cutoff_time:
                    filtered_news.append(item)
            except:
                # 如果解析时间失败,保留该新闻
                filtered_news.append(item)

        filtered_news = filtered_news[:limit]
        logger.info(f"过滤后剩余 {len(filtered_news)} 条新闻")

        # 3. LLM 分析 (如果启用)
        news_events = []

        if use_llm and self.llm_client:
            logger.info("使用 LLM 分析新闻...")
            for item in filtered_news:
                event = await self.analyze_news_with_llm(item)
                if event:
                    news_events.append(event)
        else:
            logger.info("不使用 LLM,创建默认新闻事件")
            for item in filtered_news:
                event = self._create_default_news_event(item)
                news_events.append(event)

        # 4. 过滤出高影响新闻
        high_impact_count = sum(1 for e in news_events if e.is_high_impact())
        logger.info(
            f"新闻采集完成: 共 {len(news_events)} 条, "
            f"其中 {high_impact_count} 条高影响新闻"
        )

        return news_events


# 测试代码
async def main():
    """测试新闻采集"""
    # 测试 RSS feed (无需 API key)
    collector = NewsCollector(llm_client=None)

    try:
        print("\n=== 新闻采集器 (RSS Feed) ===")
        print("数据源: CoinJournal, Cointelegraph, CoinDesk")

        # 获取最近新闻 (不使用 LLM 分析)
        events = await collector.get_recent_news(
            hours=24,
            limit=10,
            use_llm=False,  # 不使用 LLM,避免费用
            use_rss=True,
        )

        if events:
            print(f"\n采集到 {len(events)} 条新闻:")
            for i, event in enumerate(events[:5], 1):
                print(f"\n{i}. [{event.impact_level}] {event.title}")
                print(f"   来源: {event.source} | 情绪: {event.sentiment}")
                print(f"   时间: {event.dt}")
                if event.summary and len(event.summary) > len(event.title):
                    summary_preview = event.summary[:100] + "..." if len(event.summary) > 100 else event.summary
                    print(f"   摘要: {summary_preview}")
        else:
            print("未采集到新闻")

    finally:
        await collector.close()


if __name__ == "__main__":
    asyncio.run(main())
