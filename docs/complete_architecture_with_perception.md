# 完整的分层决策架构 (含感知层)

## 系统架构全景

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           感知层 (Perception)                             │
│                         持续收集外部世界的数据                             │
├─────────────────────────────────────────────────────────────────────────┤
│  数据源 1: 加密货币市场数据                                               │
│  • 价格、成交量、深度                                                    │
│  • 技术指标 (RSI、MACD、布林带等)                                        │
│  • 链上数据 (未来: 交易量、持仓地址等)                                    │
│  频率: 每 5 秒                                                           │
├─────────────────────────────────────────────────────────────────────────┤
│  数据源 2: 美股市场数据                                                   │
│  • 标普500、纳斯达克指数                                                  │
│  • 美股科技股 (AAPL、MSFT、TSLA)                                         │
│  • 加密相关股票 (COIN、MSTR)                                             │
│  频率: 每 5 分钟                                                         │
├─────────────────────────────────────────────────────────────────────────┤
│  数据源 3: 宏观经济数据                                                   │
│  • 美联储利率                                                            │
│  • CPI、非农就业数据                                                     │
│  • 美元指数 (DXY)                                                        │
│  • 黄金、原油价格                                                        │
│  频率: 每小时 (数据更新不频繁)                                            │
├─────────────────────────────────────────────────────────────────────────┤
│  数据源 4: 市场情绪数据                                                   │
│  • 恐慌贪婪指数 (Fear & Greed Index)                                     │
│  • 资金费率 (Funding Rate)                                               │
│  • 多空比 (Long/Short Ratio)                                             │
│  • 社交媒体情绪 (未来: Twitter、Reddit)                                  │
│  频率: 每 10 分钟                                                        │
├─────────────────────────────────────────────────────────────────────────┤
│  数据源 5: 新闻事件                                                       │
│  • 加密货币新闻 (CoinDesk、CoinTelegraph)                                │
│  • 财经新闻 (Bloomberg、Reuters)                                         │
│  • 政策监管新闻                                                          │
│  • 重大事件提取 (使用 LLM 总结)                                           │
│  频率: 每 30 分钟                                                        │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
                    所有数据汇总到 MarketEnvironment
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                        战略层 (Strategist)                                │
│                      每小时 1 次 - 宏观市场分析                           │
├─────────────────────────────────────────────────────────────────────────┤
│  输入 (来自感知层):                                                       │
│  • MarketEnvironment (所有外部数据的汇总)                                │
│  • 所有币种的技术面概览                                                   │
│  • 历史经验和反思                                                        │
├─────────────────────────────────────────────────────────────────────────┤
│  LLM 分析任务:                                                           │
│  1. 宏观环境判断: 牛市/熊市/震荡/恐慌                                     │
│  2. 风险评估: 当前市场整体风险等级                                        │
│  3. 市场主线: 当前市场的核心驱动逻辑                                      │
│     例如: "美联储降息预期+ETF资金流入→牛市"                               │
│  4. 币种筛选: 从50+币种中选出5-10个最值得关注的                           │
│  5. 资产配置: 建议各币种的权重和现金比例                                  │
├─────────────────────────────────────────────────────────────────────────┤
│  输出: MarketRegime                                                      │
│  • regime: 市场状态                                                      │
│  • recommended_symbols: 推荐币种列表                                     │
│  • risk_level: 风险等级                                                  │
│  • market_narrative: 市场主线                                            │
│  • cash_ratio: 建议现金比例                                              │
│  • 有效期: 1 小时                                                        │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                         战术层 (Trader)                                   │
│                    每 3-5 分钟 - 具体交易决策                             │
├─────────────────────────────────────────────────────────────────────────┤
│  输入:                                                                   │
│  • MarketRegime (来自战略层)                                             │
│  • 推荐币种的详细技术指标 (来自感知层)                                    │
│  • 当前账户状态 (余额、持仓、盈亏)                                        │
├─────────────────────────────────────────────────────────────────────────┤
│  LLM 分析任务:                                                           │
│  1. 批量分析推荐币种的技术面                                              │
│  2. 结合战略判断,评估每个币种的机会                                       │
│  3. 考虑账户状态,制定具体交易计划                                         │
│  4. 输出每个币种的交易信号                                                │
├─────────────────────────────────────────────────────────────────────────┤
│  输出: Dict[symbol, TradingSignal]                                       │
│  • 每个推荐币种一个信号                                                   │
│  • 信号类型: 开多/平多/持有等                                             │
│  • 具体参数: 价格、数量、止损、止盈                                       │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                          执行层 (Execution)                               │
│                            实时 - 订单执行                                │
├─────────────────────────────────────────────────────────────────────────┤
│  • 风险校验                                                              │
│  • 并行执行订单                                                          │
│  • 止损止盈监控 (无需 LLM)                                               │
│  • 持仓管理                                                              │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 感知层数据模型

### MarketEnvironment - 市场环境汇总

```python
from datetime import datetime
from typing import Dict, List, Optional
from pydantic import BaseModel, Field
from decimal import Decimal


class MacroData(BaseModel):
    """宏观经济数据"""

    # 美联储
    fed_rate: Optional[float] = Field(None, description="联邦基金利率 (%)")
    fed_rate_trend: Optional[str] = Field(None, description="利率趋势: raising/cutting/holding")

    # 经济指标
    cpi: Optional[float] = Field(None, description="CPI 通胀率 (%)")
    unemployment: Optional[float] = Field(None, description="失业率 (%)")

    # 市场指标
    dxy: Optional[float] = Field(None, description="美元指数")
    dxy_change_24h: Optional[float] = Field(None, description="美元指数24h变化 (%)")
    gold_price: Optional[float] = Field(None, description="黄金价格 (USD/oz)")
    oil_price: Optional[float] = Field(None, description="原油价格 (USD/barrel)")


class StockMarketData(BaseModel):
    """美股市场数据"""

    # 指数
    sp500: Optional[float] = Field(None, description="标普500指数")
    sp500_change_24h: Optional[float] = Field(None, description="标普500 24h变化 (%)")
    nasdaq: Optional[float] = Field(None, description="纳斯达克指数")
    nasdaq_change_24h: Optional[float] = Field(None, description="纳斯达克 24h变化 (%)")

    # 加密相关股票
    coin_stock: Optional[float] = Field(None, description="COIN 股价")
    mstr_stock: Optional[float] = Field(None, description="MSTR 股价")

    # 相关性
    correlation_with_crypto: Optional[float] = Field(
        None, ge=-1, le=1, description="与加密货币的相关性"
    )


class SentimentData(BaseModel):
    """市场情绪数据"""

    # 恐慌贪婪指数
    fear_greed_index: Optional[int] = Field(
        None, ge=0, le=100, description="恐慌贪婪指数 (0=极度恐慌, 100=极度贪婪)"
    )
    fear_greed_label: Optional[str] = Field(
        None, description="情绪标签: extreme_fear/fear/neutral/greed/extreme_greed"
    )

    # 资金费率
    btc_funding_rate: Optional[float] = Field(None, description="BTC 资金费率 (%)")
    eth_funding_rate: Optional[float] = Field(None, description="ETH 资金费率 (%)")

    # 多空比
    btc_long_short_ratio: Optional[float] = Field(None, description="BTC 多空比")

    # 社交媒体 (未来)
    twitter_sentiment: Optional[float] = Field(
        None, ge=-1, le=1, description="Twitter 情绪评分"
    )


class NewsEvent(BaseModel):
    """新闻事件"""

    timestamp: int = Field(..., description="事件时间戳")
    title: str = Field(..., description="新闻标题")
    summary: str = Field(..., description="新闻摘要")
    source: str = Field(..., description="新闻来源")
    impact_level: str = Field(
        ..., description="影响等级: low/medium/high/critical"
    )
    sentiment: str = Field(
        ..., description="情绪: positive/neutral/negative"
    )
    related_symbols: List[str] = Field(
        default_factory=list, description="相关币种"
    )


class MarketEnvironment(BaseModel):
    """
    市场环境数据汇总

    由感知层每小时生成,供战略层分析使用
    """

    timestamp: int = Field(..., description="生成时间戳 (毫秒)")
    dt: datetime = Field(..., description="生成时间")

    # 宏观数据
    macro: Optional[MacroData] = Field(None, description="宏观经济数据")

    # 美股数据
    stock_market: Optional[StockMarketData] = Field(None, description="美股市场数据")

    # 情绪数据
    sentiment: Optional[SentimentData] = Field(None, description="市场情绪数据")

    # 新闻事件 (最近24小时)
    recent_news: List[NewsEvent] = Field(
        default_factory=list, description="最近的重大新闻"
    )

    # 加密市场概览
    crypto_market_cap: Optional[Decimal] = Field(
        None, description="加密货币总市值"
    )
    btc_dominance: Optional[float] = Field(
        None, ge=0, le=100, description="BTC 市值占比 (%)"
    )

    def get_summary(self) -> str:
        """获取环境摘要"""
        parts = []

        if self.macro and self.macro.fed_rate:
            parts.append(f"利率: {self.macro.fed_rate}%")

        if self.stock_market and self.stock_market.sp500_change_24h:
            parts.append(f"标普: {self.stock_market.sp500_change_24h:+.2f}%")

        if self.sentiment and self.sentiment.fear_greed_index:
            parts.append(f"情绪: {self.sentiment.fear_greed_label}")

        if self.recent_news:
            high_impact = [n for n in self.recent_news if n.impact_level == "high"]
            if high_impact:
                parts.append(f"{len(high_impact)}条重大新闻")

        return " | ".join(parts) if parts else "数据采集中"
```

---

## 感知层采集器设计

### 目录结构

```
src/perception/
├── market_data.py          # 现有: 加密货币市场数据
├── indicators.py           # 现有: 技术指标计算
├── symbol_mapper.py        # 现有: 交易对映射
├── macro_data.py           # 新增: 宏观经济数据采集
├── stock_market.py         # 新增: 美股数据采集
├── sentiment.py            # 新增: 市场情绪数据采集
├── news_collector.py       # 新增: 新闻采集
└── environment_builder.py  # 新增: 汇总构建 MarketEnvironment
```

### 各采集器职责

#### 1. MacroDataCollector (宏观数据)

```python
class MacroDataCollector:
    """采集宏观经济数据"""

    async def get_macro_data(self) -> MacroData:
        """
        获取宏观数据

        数据源:
        - FRED (美联储经济数据库) API
        - Yahoo Finance
        - Investing.com
        """
        return MacroData(
            fed_rate=await self._get_fed_rate(),
            dxy=await self._get_dxy(),
            gold_price=await self._get_gold_price(),
            # ...
        )
```

#### 2. StockMarketCollector (美股数据)

```python
class StockMarketCollector:
    """采集美股市场数据"""

    async def get_stock_data(self) -> StockMarketData:
        """
        获取美股数据

        数据源:
        - Yahoo Finance API
        - Alpha Vantage API
        - Finnhub API
        """
        return StockMarketData(
            sp500=await self._get_sp500(),
            nasdaq=await self._get_nasdaq(),
            coin_stock=await self._get_ticker("COIN"),
            # ...
        )
```

#### 3. SentimentCollector (情绪数据)

```python
class SentimentCollector:
    """采集市场情绪数据"""

    async def get_sentiment_data(self) -> SentimentData:
        """
        获取情绪数据

        数据源:
        - Alternative.me (恐慌贪婪指数)
        - Binance/Bybit (资金费率)
        - Coinglass (多空比)
        """
        return SentimentData(
            fear_greed_index=await self._get_fear_greed(),
            btc_funding_rate=await self._get_funding_rate("BTC"),
            # ...
        )
```

#### 4. NewsCollector (新闻采集)

```python
class NewsCollector:
    """采集加密货币新闻"""

    async def get_recent_news(self, hours=24) -> List[NewsEvent]:
        """
        获取最近的新闻

        数据源:
        - CoinDesk API
        - CryptoCompare News API
        - NewsAPI

        处理:
        - 使用 LLM 总结新闻
        - 提取影响等级和情绪
        - 识别相关币种
        """
        raw_news = await self._fetch_news(hours)
        return [await self._process_news(n) for n in raw_news]

    async def _process_news(self, raw: dict) -> NewsEvent:
        """使用 LLM 处理新闻"""
        # 调用 LLM 总结和分类
        result = await self.llm.analyze_news(raw["content"])
        return NewsEvent(
            timestamp=raw["timestamp"],
            title=raw["title"],
            summary=result["summary"],
            impact_level=result["impact"],
            sentiment=result["sentiment"],
            related_symbols=result["symbols"],
        )
```

#### 5. EnvironmentBuilder (环境构建器)

```python
class EnvironmentBuilder:
    """汇总所有感知数据,构建 MarketEnvironment"""

    def __init__(self):
        self.macro_collector = MacroDataCollector()
        self.stock_collector = StockMarketCollector()
        self.sentiment_collector = SentimentCollector()
        self.news_collector = NewsCollector()

    async def build_environment(self) -> MarketEnvironment:
        """
        并行采集所有数据,构建环境

        频率: 每小时一次 (供战略层使用)
        """
        # 并行采集
        macro, stock, sentiment, news = await asyncio.gather(
            self.macro_collector.get_macro_data(),
            self.stock_collector.get_stock_data(),
            self.sentiment_collector.get_sentiment_data(),
            self.news_collector.get_recent_news(24),
            return_exceptions=True
        )

        # 处理异常
        if isinstance(macro, Exception):
            logger.error(f"宏观数据采集失败: {macro}")
            macro = None

        # 构建环境
        now = datetime.now(timezone.utc)
        return MarketEnvironment(
            timestamp=int(now.timestamp() * 1000),
            dt=now,
            macro=macro,
            stock_market=stock,
            sentiment=sentiment,
            recent_news=news if not isinstance(news, Exception) else [],
        )
```

---

## 完整数据流

### 主循环伪代码

```python
async def main_loop():
    """完整的主循环"""

    # 启动持续的市场数据采集 (加密货币价格、技术指标)
    asyncio.create_task(crypto_data_collection_loop())  # 每5秒

    # 战略层循环 (每小时)
    async def strategist_loop():
        while True:
            # 1. 构建市场环境 (汇总所有外部数据)
            environment = await environment_builder.build_environment()
            logger.info(f"环境更新: {environment.get_summary()}")

            # 2. 获取加密市场概览
            crypto_overview = await get_crypto_market_overview()

            # 3. LLM 战略分析
            regime = await strategist.analyze_market(
                environment=environment,  # 宏观、美股、情绪、新闻
                crypto_overview=crypto_overview,  # 加密市场技术面
            )
            logger.info(f"战略更新: {regime.get_summary()}")

            # 4. 缓存供战术层使用
            await cache.set("current_regime", regime, ttl=3600)
            await cache.set("current_environment", environment, ttl=3600)

            # 5. 等待1小时
            await asyncio.sleep(3600)

    # 战术层循环 (每3-5分钟)
    async def trader_loop():
        while True:
            # 1. 获取战略判断
            regime = await cache.get("current_regime")
            if not regime or not regime.is_valid():
                await asyncio.sleep(60)
                continue

            # 2. 只分析推荐币种
            symbols = regime.get_recommended_symbols_for_trading()

            # 3. 批量生成信号
            signals = await trader.batch_generate_signals(
                symbols_snapshots=get_snapshots(symbols),
                regime=regime,
                portfolio=await portfolio_manager.get_portfolio()
            )

            # 4. 执行
            await execute_signals(signals)

            # 5. 等待3-5分钟
            await asyncio.sleep(180)

    # 并发运行两个循环
    await asyncio.gather(
        strategist_loop(),
        trader_loop(),
    )
```

---

## 实施优先级

### Phase 1: 数据模型 (已完成 ✅)
- [x] MarketRegime
- [ ] MarketEnvironment
- [ ] MacroData, StockMarketData, SentimentData
- [ ] NewsEvent

### Phase 2: 基础感知器 (1-2天)
- [ ] SentimentCollector (恐慌贪婪指数 + 资金费率)
- [ ] EnvironmentBuilder (先用部分数据)
- [ ] 集成到战略层

### Phase 3: 扩展感知器 (3-5天)
- [ ] MacroDataCollector (宏观数据)
- [ ] StockMarketCollector (美股数据)
- [ ] NewsCollector (新闻采集 + LLM处理)

### Phase 4: 优化 (持续)
- [ ] 社交媒体情绪分析
- [ ] 链上数据
- [ ] 更多数据源

---

## 总结

通过这个完整架构:

1. **感知层**: 全方位感知外部世界
   - 加密市场、美股、宏观、情绪、新闻

2. **战略层**: 基于全局数据做宏观判断
   - 每小时分析一次
   - 输出市场状态和币种推荐

3. **战术层**: 基于战略指引做具体交易
   - 每3-5分钟分析一次
   - 只关注推荐币种

4. **执行层**: 忠实执行交易决策
   - 风控、订单、监控

这样的架构:
- ✅ Token 节省 70-90%
- ✅ 决策质量大幅提升 (有更多数据支持)
- ✅ 易于扩展 (随时可以添加新数据源)
- ✅ 符合实际交易逻辑
