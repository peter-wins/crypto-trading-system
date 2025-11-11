# 系统可扩展性优化方案

## 当前问题

### 问题 1：串行处理导致时间线性增长

**当前架构**：
```python
for symbol in self.symbols:  # 顺序处理
    await process_symbol(symbol)  # 等待完成才处理下一个
```

**时间成本**：
| 币种数量 | 每个处理时间 | 总耗时 | 备注 |
|---------|-------------|--------|------|
| 2个 | 30秒 | 1分钟 | 当前配置 |
| 10个 | 30秒 | 5分钟 | 😰 |
| 50个 | 30秒 | 25分钟 | 💀 完全不可用 |

### 问题 2：每个币种都调用一次 LLM

**当前流程**：
```
BTC: 准备数据 → 调用LLM → 生成信号 → 执行订单
ETH: 准备数据 → 调用LLM → 生成信号 → 执行订单
SOL: 准备数据 → 调用LLM → 生成信号 → 执行订单
...
```

**成本问题**：
- LLM API 调用成本：N 个币种 × $0.01/次 = $0.10（10个币种）
- 延迟累加：N 个币种 × 5秒 = 50秒（10个币种）

---

## 优化方案

### 方案 1：并行处理（推荐，短期）

**原理**：同时处理多个币种，而不是排队等待

**实现**：
```python
# 修改前（串行）
for symbol in self.symbols:
    await process_symbol(symbol)  # 等待完成

# 修改后（并行）
tasks = [process_symbol(symbol) for symbol in self.symbols]
await asyncio.gather(*tasks)  # 并发执行
```

**效果**：
| 币种数量 | 串行耗时 | 并行耗时 | 提升 |
|---------|---------|---------|------|
| 2个 | 1分钟 | 30秒 | 2x |
| 10个 | 5分钟 | 30秒 | 10x |
| 50个 | 25分钟 | 30秒 | 50x |

**优点**：
- ✅ 简单，只需改几行代码
- ✅ 立即生效
- ✅ 线性扩展

**缺点**：
- ⚠️ 仍然需要多次调用 LLM（成本高）
- ⚠️ 并发过高可能触发 API 限流

---

### 方案 2：批量分析（推荐，长期）

**原理**：一次 LLM 调用分析所有币种，而不是每个币种调用一次

**当前模式**：
```
调用 1: 分析 BTC
调用 2: 分析 ETH
调用 3: 分析 SOL
```

**批量模式**：
```
调用 1: 同时分析 BTC + ETH + SOL，返回所有信号
```

**Prompt 示例**：
```
你需要分析以下交易对的交易机会：

=== BTC/USDC:USDC ===
市场数据:
  价格: 75234.50
  RSI: 45.32
  MACD: 金叉
  ...

=== ETH/USDC:USDC ===
市场数据:
  价格: 3432.60
  RSI: 52.10
  MACD: 死叉
  ...

请输出 JSON 数组，每个币种一个信号：
[
  {"symbol": "BTC/USDC:USDC", "signal_type": "enter_long", ...},
  {"symbol": "ETH/USDC:USDC", "signal_type": "hold", ...}
]
```

**效果**：
| 币种数量 | 当前成本 | 批量成本 | 节省 |
|---------|---------|---------|------|
| 2个 | $0.02 | $0.01 | 50% |
| 10个 | $0.10 | $0.02 | 80% |
| 50个 | $0.50 | $0.05 | 90% |

**优点**：
- ✅ 大幅降低 LLM 成本
- ✅ 减少 API 调用次数
- ✅ LLM 可以跨币种比较（如："BTC 强于 ETH，优先做多 BTC"）
- ✅ 更快的响应速度

**缺点**：
- ⚠️ 需要重构 prompt 和响应解析
- ⚠️ 单次 prompt 变长（但仍在限制内）

---

### 方案 3：分层决策（推荐，终极方案）

**架构**：
```
Layer 1: Strategist (portfolio level, 每小时1次)
  ↓
  分析整个市场，输出：
  - 市场regime（牛/熊/震荡）
  - 资产配置建议（哪些币种值得关注）
  - 风险参数调整

Layer 2: Trader (symbol level, 每分钟1次)
  ↓
  批量分析策略推荐的币种：
  - 输入：Layer 1 的策略 + 所有币种的市场数据
  - 输出：每个币种的具体交易信号

Layer 3: Execution (order level, 实时)
  ↓
  并行执行所有订单
```

**伪代码**：
```python
# Layer 1: 战略层（低频）
strategy = await strategist.analyze_portfolio()  # 1小时1次
active_symbols = strategy.recommended_symbols    # 只关注5-10个币种

# Layer 2: 战术层（中频）
signals = await trader.batch_analyze(active_symbols)  # 批量分析
signals = [s for s in signals if s.confidence > 0.6]  # 过滤低置信度

# Layer 3: 执行层（高频）
tasks = [execute_signal(signal) for signal in signals]
await asyncio.gather(*tasks)  # 并行执行
```

**效果**：
- ✅ **智能筛选**：不分析所有50个币种，只分析最有潜力的5-10个
- ✅ **批量处理**：一次分析多个币种
- ✅ **并行执行**：同时下单
- ✅ **成本优化**：减少无效分析

---

## 实施优先级

### Phase 1：快速见效（1-2小时）

**实施方案 1：并行处理**

修改 `main.py`：
```python
# 当前代码 (line 446)
for symbol in self.symbols:
    await self._process_symbol_with_cached_data(symbol, snapshot)

# 优化后
tasks = []
for symbol in self.symbols:
    snapshot = self._last_market_snapshot.get(symbol)
    if snapshot:
        tasks.append(self._process_symbol_with_cached_data(symbol, snapshot))

# 并发执行，但限制并发数避免 API 限流
from asyncio import Semaphore
semaphore = Semaphore(5)  # 最多5个并发

async def process_with_limit(symbol, snapshot):
    async with semaphore:
        await self._process_symbol_with_cached_data(symbol, snapshot)

tasks = [process_with_limit(symbol, snapshot)
         for symbol, snapshot in snapshots.items()]
await asyncio.gather(*tasks, return_exceptions=True)
```

**预期效果**：
- 2个币种：60秒 → 30秒
- 10个币种：5分钟 → 1分钟

---

### Phase 2：成本优化（1天）

**实施方案 2：批量分析**

1. **新增 `batch_generate_signals` 方法**：

```python
# src/decision/trader.py

async def batch_generate_signals(
    self,
    symbols_data: Dict[str, Dict[str, Any]],  # {symbol: snapshot}
    strategy: StrategyConfig,
    portfolio: Portfolio,
) -> Dict[str, TradingSignal]:
    """
    批量分析多个币种，一次 LLM 调用

    Args:
        symbols_data: {symbol: market_snapshot}
        strategy: 策略配置
        portfolio: 持仓信息

    Returns:
        {symbol: TradingSignal}
    """
    # 构建批量 prompt
    context = self._build_batch_context(symbols_data, strategy, portfolio)
    prompt = PromptTemplates.build_batch_trader_prompt(context)

    # 调用 LLM
    response = await self._chat_with_tools(...)

    # 解析批量响应
    signals = self._parse_batch_signals(response)
    return signals
```

2. **修改主循环**：

```python
# main.py

async def run(self):
    while self.running:
        # 收集所有币种的 snapshot
        snapshots = {
            symbol: self._last_market_snapshot.get(symbol)
            for symbol in self.symbols
            if symbol in self._last_market_snapshot
        }

        # 批量生成信号（1次 LLM 调用）
        signals = await self.trader.batch_generate_signals(
            snapshots, strategy, portfolio
        )

        # 并行执行所有信号
        tasks = [
            self._execute_signal(symbol, signal, ...)
            for symbol, signal in signals.items()
        ]
        await asyncio.gather(*tasks, return_exceptions=True)
```

**预期效果**：
- LLM 调用次数：10次 → 1次
- 成本：$0.10 → $0.02

---

### Phase 3：架构升级（3-5天）

**实施方案 3：分层决策**

1. **Strategist 层**：
   - 每小时分析一次市场
   - 输出推荐的币种列表（如前10个）
   - 动态调整风险参数

2. **Trader 层**：
   - 只分析 Strategist 推荐的币种
   - 批量生成信号

3. **Execution 层**：
   - 并行执行订单

**预期效果**：
- 50个币种 → 只分析10个
- 总耗时：25分钟 → 30秒
- 成本：$0.50 → $0.05

---

## 其他优化建议

### 1. 信号缓存

**问题**：市场数据每5秒更新一次，但决策每60秒才执行一次，中间的数据更新可能触发重复信号。

**方案**：
```python
# 缓存最近的信号，避免重复执行
self._signal_cache = {}  # {symbol: (signal, timestamp)}

def should_execute_signal(self, symbol, new_signal):
    cached = self._signal_cache.get(symbol)
    if not cached:
        return True

    old_signal, timestamp = cached
    # 如果信号类型相同且时间在5分钟内，跳过
    if (old_signal.signal_type == new_signal.signal_type and
        (now - timestamp).seconds < 300):
        return False

    return True
```

### 2. 智能限流

**问题**：并发太多可能触发 API 限流。

**方案**：
```python
from asyncio import Semaphore

class RateLimiter:
    def __init__(self, max_concurrent=5, calls_per_minute=20):
        self.semaphore = Semaphore(max_concurrent)
        self.calls = []
        self.limit = calls_per_minute

    async def acquire(self):
        async with self.semaphore:
            # 清理1分钟前的记录
            now = time.time()
            self.calls = [t for t in self.calls if now - t < 60]

            # 如果超过限制，等待
            if len(self.calls) >= self.limit:
                wait_time = 60 - (now - self.calls[0])
                await asyncio.sleep(wait_time)

            self.calls.append(now)
```

### 3. 优先级队列

**问题**：所有币种同等优先级，但有些更值得关注。

**方案**：
```python
# 根据波动率、成交量等排序
priority_symbols = sorted(
    self.symbols,
    key=lambda s: self._calculate_priority(s),
    reverse=True
)

# 优先处理高优先级的币种
for symbol in priority_symbols[:10]:  # 只处理前10个
    await process_symbol(symbol)
```

---

## 推荐实施路径

### 立即实施（今天）
✅ **方案 1：并行处理**
- 修改量：< 20行代码
- 见效时间：立即
- 收益：2-10倍提速

### 本周实施
✅ **方案 2：批量分析**
- 修改量：~200行代码
- 见效时间：1-2天
- 收益：80-90% 成本降低

### 下周实施
✅ **方案 3：分层决策**
- 修改量：~500行代码
- 见效时间：3-5天
- 收益：10-50倍扩展能力

### 持续优化
- 信号缓存
- 智能限流
- 优先级队列
- 性能监控

---

## 预期效果对比

### 当前架构（未优化）
| 币种数 | 处理时间 | LLM调用 | 成本/轮 |
|--------|---------|---------|---------|
| 2 | 1分钟 | 2次 | $0.02 |
| 10 | 5分钟 | 10次 | $0.10 |
| 50 | 25分钟 | 50次 | $0.50 |

### Phase 1：并行处理
| 币种数 | 处理时间 | LLM调用 | 成本/轮 |
|--------|---------|---------|---------|
| 2 | 30秒 | 2次 | $0.02 |
| 10 | 1分钟 | 10次 | $0.10 |
| 50 | 2分钟 | 50次 | $0.50 |

### Phase 2：批量分析
| 币种数 | 处理时间 | LLM调用 | 成本/轮 |
|--------|---------|---------|---------|
| 2 | 30秒 | 1次 | $0.01 |
| 10 | 30秒 | 1次 | $0.02 |
| 50 | 1分钟 | 1次 | $0.05 |

### Phase 3：分层决策
| 币种数 | 处理时间 | LLM调用 | 成本/轮 |
|--------|---------|---------|---------|
| 2 | 15秒 | 1次 | $0.01 |
| 10 | 20秒 | 1次 | $0.01 |
| 50 | 30秒 | 1次 | $0.02 |

---

**结论**：通过三阶段优化，可以实现：
- ⚡ **50倍性能提升**：25分钟 → 30秒
- 💰 **25倍成本降低**：$0.50 → $0.02
- 📈 **无限扩展能力**：支持50+ 币种

**建议先实施 Phase 1（并行处理），立即见效！**
