# 分层决策架构设计

## 架构概览

```
┌─────────────────────────────────────────────────────────┐
│  战略层 (Strategist)                                     │
│  频率: 每小时 1 次                                       │
│  职责: 宏观市场分析                                      │
├─────────────────────────────────────────────────────────┤
│  输入:                                                   │
│  • 宏观经济数据 (未来: GDP、通胀率、利率等)              │
│  • 市场情绪指标 (未来: 恐慌贪婪指数、社交媒体情绪)       │
│  • 新闻事件 (未来: 重大政策、技术突破、黑天鹅事件)       │
│  • 所有币种的技术面概览                                  │
│  • 历史经验和反思                                        │
├─────────────────────────────────────────────────────────┤
│  输出 (MarketRegime):                                   │
│  • regime: "牛市" | "熊市" | "震荡" | "恐慌"            │
│  • confidence: 0-1 (对判断的信心)                       │
│  • recommended_symbols: [币种列表] (值得关注的)          │
│  • risk_level: "低" | "中" | "高" | "极高"              │
│  • market_narrative: 市场主线/逻辑 (如"美联储降息预期")  │
│  • time_horizon: "短期" | "中期" | "长期"               │
│  • suggested_allocation: {symbol: 建议权重}              │
└─────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────┐
│  战术层 (Trader)                                         │
│  频率: 每 3-5 分钟                                       │
│  职责: 具体交易决策                                      │
├─────────────────────────────────────────────────────────┤
│  输入:                                                   │
│  • 战略层的 MarketRegime                                │
│  • 推荐币种的详细技术指标                                │
│  • 当前账户状态 (余额、持仓、盈亏)                       │
│  • 风险参数                                             │
├─────────────────────────────────────────────────────────┤
│  输出 (TradingSignals):                                 │
│  • {symbol: TradingSignal} (具体交易信号)              │
│  • 每个信号包含: 方向、数量、止损、止盈等                │
└─────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────┐
│  执行层 (Execution)                                      │
│  频率: 实时                                              │
│  职责: 订单执行和风控                                    │
├─────────────────────────────────────────────────────────┤
│  • 风险校验                                             │
│  • 订单执行 (并行)                                      │
│  • 止损止盈监控 (无需 LLM)                              │
│  • 持仓管理                                             │
└─────────────────────────────────────────────────────────┘
```

---

## 数据模型

### 1. MarketRegime (战略层输出)

```python
from enum import Enum
from pydantic import BaseModel, Field
from typing import Dict, List, Optional

class RegimeType(str, Enum):
    BULL = "bull"          # 牛市
    BEAR = "bear"          # 熊市
    SIDEWAYS = "sideways"  # 震荡
    PANIC = "panic"        # 恐慌

class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    EXTREME = "extreme"

class MarketRegime(BaseModel):
    """战略层的市场判断"""

    # 基础判断
    regime: RegimeType = Field(..., description="市场状态")
    confidence: float = Field(..., ge=0, le=1, description="判断信心")

    # 币种筛选
    recommended_symbols: List[str] = Field(
        default_factory=list,
        description="值得关注的币种列表 (按优先级排序)"
    )
    max_symbols_to_trade: int = Field(
        default=5,
        description="建议同时交易的最大币种数"
    )

    # 风险评估
    risk_level: RiskLevel = Field(..., description="当前市场风险等级")

    # 市场叙事
    market_narrative: str = Field(..., description="市场主线/核心逻辑")
    key_drivers: List[str] = Field(
        default_factory=list,
        description="关键驱动因素"
    )

    # 策略建议
    time_horizon: str = Field(..., description="建议持仓周期")
    suggested_allocation: Dict[str, float] = Field(
        default_factory=dict,
        description="建议的资产配置 {symbol: 权重}"
    )
    cash_ratio: float = Field(
        default=0.3,
        ge=0,
        le=1,
        description="建议现金比例"
    )

    # 时间戳
    timestamp: int = Field(..., description="生成时间戳(毫秒)")
    valid_until: int = Field(..., description="有效期至(毫秒)")

    # 原因说明
    reasoning: str = Field(..., description="判断理由")

    # 未来扩展字段
    macro_indicators: Optional[Dict[str, any]] = Field(
        None,
        description="宏观指标 (未来: GDP、利率等)"
    )
    sentiment_score: Optional[float] = Field(
        None,
        ge=-1,
        le=1,
        description="市场情绪评分 (未来: -1恐慌到1贪婪)"
    )
    news_events: Optional[List[Dict[str, str]]] = Field(
        None,
        description="重大新闻事件 (未来)"
    )
```

---

## 决策流程

### 阶段1: 战略层 (每小时)

```python
async def strategist_decision_loop():
    """战略层决策循环 - 每小时一次"""

    while True:
        # 1. 收集宏观数据
        macro_data = await collect_macro_data()  # 未来实现

        # 2. 分析所有币种的技术面概览
        symbols_overview = await get_symbols_overview(all_symbols)

        # 3. 查询历史经验
        past_experiences = await memory.search_similar_market_conditions()

        # 4. LLM 战略分析
        regime = await strategist.analyze_market(
            macro_data=macro_data,
            symbols_overview=symbols_overview,
            experiences=past_experiences
        )

        # 5. 缓存战略判断 (供战术层使用)
        await cache.set("current_regime", regime, ttl=3600)

        logger.info(f"战略更新: {regime.regime.value} | 风险: {regime.risk_level.value}")
        logger.info(f"推荐币种: {regime.recommended_symbols[:5]}")

        # 6. 等待1小时
        await asyncio.sleep(3600)
```

### 阶段2: 战术层 (每3-5分钟)

```python
async def trader_decision_loop():
    """战术层决策循环 - 每3-5分钟"""

    while True:
        # 1. 获取最新战略判断
        regime = await cache.get("current_regime")
        if not regime:
            logger.warning("无战略判断,使用默认策略")
            regime = get_default_regime()

        # 2. 只分析战略层推荐的币种
        active_symbols = regime.recommended_symbols[:regime.max_symbols_to_trade]

        if not active_symbols:
            logger.info("战略层无推荐币种,本轮跳过")
            await asyncio.sleep(180)  # 3分钟
            continue

        # 3. 获取这些币种的详细市场数据
        snapshots = {}
        for symbol in active_symbols:
            snapshot = await get_market_snapshot(symbol)
            if snapshot:
                snapshots[symbol] = snapshot

        # 4. 获取账户状态
        portfolio = await portfolio_manager.get_current_portfolio()

        # 5. 批量生成交易信号
        signals = await trader.batch_generate_signals(
            symbols_snapshots=snapshots,
            regime=regime,           # 传入战略判断
            portfolio=portfolio
        )

        # 6. 执行信号
        await execute_signals(signals)

        # 7. 等待3-5分钟
        await asyncio.sleep(180)  # 可配置
```

---

## Token 优化效果

### 优化前 (当前架构)

| 层次 | 频率 | 币种数 | Token/次 | 每小时 Token | 每天 Token |
|------|------|--------|----------|--------------|-----------|
| Trader | 每分钟 | 2 | 2000 | 120,000 | 2,880,000 |
| **合计** | - | - | - | **120,000** | **2,880,000** |

成本: **$0.40/天**

### 优化后 (分层架构)

| 层次 | 频率 | 币种数 | Token/次 | 每小时 Token | 每天 Token |
|------|------|--------|----------|--------------|-----------|
| Strategist | 每小时 | 10 | 3000 | 3,000 | 72,000 |
| Trader | 每3分钟 | 5 | 1500 | 30,000 | 720,000 |
| **合计** | - | - | - | **33,000** | **792,000** |

成本: **$0.11/天** (节省 **72.5%**)

### 扩展到20个币种

| 层次 | 频率 | 币种数 | Token/次 | 每小时 Token | 每天 Token |
|------|------|--------|----------|--------------|-----------|
| Strategist | 每小时 | 20 | 4000 | 4,000 | 96,000 |
| Trader | 每3分钟 | 8 | 2000 | 40,000 | 960,000 |
| **合计** | - | - | - | **44,000** | **1,056,000** |

成本: **$0.15/天** (原方案需要 **$4.00/天**)

---

## 实施计划

### Phase 1: 基础分层 (1-2天)

**目标**: 实现战略层和战术层的基本分离

- [x] 定义 MarketRegime 数据模型
- [ ] 增强 Strategist 的宏观分析能力
- [ ] 修改 Trader 接受 MarketRegime 输入
- [ ] 实现决策频率控制
- [ ] 集成到主循环

### Phase 2: 优化提示词 (1天)

**目标**: 让每层专注于自己的职责

- [ ] 简化 Strategist 提示词 (只输出市场判断)
- [ ] 简化 Trader 提示词 (接收战略判断,专注战术)
- [ ] 压缩数据格式

### Phase 3: 扩展数据源 (未来)

**目标**: 增加战略层的数据输入

- [ ] 集成宏观经济数据 API
- [ ] 集成市场情绪指标
- [ ] 集成新闻事件源
- [ ] 实现情绪分析

---

## 配置参数

```python
# config.yaml

decision:
  # 战略层
  strategist:
    enabled: true
    interval: 3600  # 1小时
    symbols_pool: 20  # 分析的币种池
    max_recommended: 10  # 最多推荐多少个

  # 战术层
  trader:
    enabled: true
    interval: 180  # 3分钟
    max_concurrent_symbols: 5  # 同时交易最多5个币种
    use_regime: true  # 是否使用战略判断

  # 回退策略
  fallback:
    use_default_regime: true  # 战略层失败时使用默认判断
```

---

## 优势总结

1. **Token 节省 70-90%**
   - 战略层低频 (1小时)
   - 战术层只分析筛选后的币种

2. **决策质量提升**
   - 战略层提供宏观视角
   - 战术层专注具体执行
   - 避免短视的频繁交易

3. **可扩展性强**
   - 可以监控50+币种
   - 战略层筛选出5-10个重点关注
   - 战术层只处理高质量机会

4. **未来可扩展**
   - 战略层可以接入更多数据源
   - 易于添加宏观指标、新闻、情绪等
   - 为量化策略留出空间

5. **风险控制更好**
   - 战略层把控整体方向
   - 避免在熊市/震荡市过度交易
   - 在牛市抓住主要机会
