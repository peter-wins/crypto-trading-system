# Token 优化方案

## 当前问题

### Token 消耗分析 (2个币种)
| 项目 | Token数 | 频率 | 每小时 | 每天 |
|------|---------|------|--------|------|
| 系统提示词 | 300 | 每次 | 18,000 | 432,000 |
| 批量用户提示词 | 1,200 | 每次 | 72,000 | 1,728,000 |
| LLM 响应 | 500 | 每次 | 30,000 | 720,000 |
| **合计** | **2,000** | 60次/小时 | **120,000** | **2,880,000** |

**成本估算** (DeepSeek $0.14/M tokens):
- 每小时: $0.017
- 每天: $0.40
- 每月: $12.00

---

## 优化方案

### 方案 1: 增量决策 ⭐ 推荐

**原理**: 只在市场有显著变化时才调用 LLM

#### 1.1 市场变化检测

```python
def has_significant_change(current_snapshot, last_snapshot) -> bool:
    """检测市场是否有显著变化"""

    # 价格变化超过 0.5%
    price_change = abs(current_snapshot['price'] - last_snapshot['price']) / last_snapshot['price']
    if price_change > 0.005:
        return True

    # RSI 变化超过 5 点
    if abs(current_snapshot['rsi'] - last_snapshot['rsi']) > 5:
        return True

    # MACD 金叉/死叉
    old_cross = last_snapshot['macd'] > last_snapshot['macd_signal']
    new_cross = current_snapshot['macd'] > current_snapshot['macd_signal']
    if old_cross != new_cross:
        return True

    # 布林带突破
    if current_snapshot['price'] > current_snapshot['bb_upper']:
        return True
    if current_snapshot['price'] < current_snapshot['bb_lower']:
        return True

    return False
```

#### 1.2 智能决策缓存

```python
class DecisionCache:
    def __init__(self, ttl_seconds=300):  # 5分钟缓存
        self.cache = {}  # {symbol: (signal, timestamp, snapshot)}
        self.ttl = ttl_seconds

    def should_regenerate(self, symbol, current_snapshot):
        """判断是否需要重新生成决策"""
        if symbol not in self.cache:
            return True

        signal, timestamp, last_snapshot = self.cache[symbol]

        # 缓存过期
        if time.time() - timestamp > self.ttl:
            return True

        # 市场有显著变化
        if has_significant_change(current_snapshot, last_snapshot):
            return True

        # 有持仓且价格接近止损/止盈
        if signal.stop_loss and abs(current_snapshot['price'] - signal.stop_loss) / current_snapshot['price'] < 0.01:
            return True

        return False

    def get(self, symbol):
        """获取缓存的信号"""
        if symbol in self.cache:
            signal, timestamp, snapshot = self.cache[symbol]
            return signal
        return None

    def set(self, symbol, signal, snapshot):
        """缓存信号"""
        self.cache[symbol] = (signal, time.time(), snapshot)
```

#### 1.3 使用示例

```python
# 在主循环中
for symbol in symbols:
    snapshot = get_market_snapshot(symbol)

    if decision_cache.should_regenerate(symbol, snapshot):
        # 需要 LLM 重新决策
        signal = await trader.generate_signal(symbol, snapshot)
        decision_cache.set(symbol, signal, snapshot)
    else:
        # 使用缓存信号
        signal = decision_cache.get(symbol)
        logger.info(f"{symbol} 市场无显著变化，使用缓存决策")
```

**预期效果**:
- Token 减少: 70-90%
- 成本: $0.40/天 → **$0.04-0.12/天**
- 响应速度更快

---

### 方案 2: 压缩提示词

#### 2.1 简化市场数据格式

**当前格式** (冗长):
```
当前市场数据:
  价格: 75234.50
  RSI(14): 45.32 (中性)
  MACD: 0.0123, Signal: 0.0115 (金叉)
  SMA快线(12): 75123.45
  SMA慢线(26): 74998.23
  布林带: 上轨=76000, 中轨=75000, 下轨=74000
```
**Token 数**: ~120

**优化格式** (紧凑):
```
BTC: P=75234.5 RSI=45 MACD=金叉 SMA=75123/74998 BB=74000-76000
```
**Token 数**: ~30

**节省**: 75%

#### 2.2 移除冗余说明

**当前**:
```
=== 分析要求 ===

**请为每个交易对独立分析：**

1. **分析市场数据**：
   - 查看价格、RSI、MACD、均线、布林带
   - 判断趋势和信号强度
...
```
**Token 数**: ~200

**优化**: 只在系统提示词中说明一次,用户提示词直接给数据

**节省**: ~200 tokens/轮

---

### 方案 3: 分层决策频率

**核心思想**: 不同类型的决策使用不同频率

```python
# 战略层 (Strategist): 每小时1次
# - 市场大势判断
# - 筛选值得关注的币种
strategy = await strategist.make_decision()  # 1次/小时

# 战术层 (Trader): 每5分钟1次,只分析战略层推荐的币种
active_symbols = strategy.recommended_symbols[:5]  # 只关注前5个
signals = await trader.batch_analyze(active_symbols)  # 12次/小时

# 执行层: 每分钟检查一次止损止盈
check_stop_loss()  # 60次/小时,无LLM调用
```

**Token 对比**:
| 方案 | Strategist | Trader | 每小时总计 |
|------|-----------|--------|-----------|
| 当前 | 0 | 60次 × 2000 | 120,000 |
| 优化 | 1次 × 3000 | 12次 × 1000 | 15,000 |

**节省**: 87.5%

---

### 方案 4: 使用更小的模型

对于简单场景,使用不同模型:

| 场景 | 当前模型 | 优化模型 | 成本 |
|------|---------|---------|------|
| HOLD 信号确认 | DeepSeek-V3 | DeepSeek-V2.5 | -50% |
| 批量分析 | DeepSeek-V3 | DeepSeek-V3 | 保持 |
| 战略决策 | DeepSeek-V3 | DeepSeek-R1 | +推理能力 |

---

## 综合优化方案 (推荐)

### 阶段 1: 增量决策 (立即实施)
- 实现市场变化检测
- 实现决策缓存
- 预期节省: 70-80%

### 阶段 2: 压缩提示词 (1-2天)
- 优化数据格式
- 移除冗余文本
- 预期节省: 额外 30-40%

### 阶段 3: 分层决策 (长期)
- 实现战略层
- 调整决策频率
- 预期节省: 额外 20-30%

---

## 预期总体效果

| 指标 | 优化前 | 阶段1 | 阶段2 | 阶段3 |
|------|--------|-------|-------|-------|
| Token/小时 | 120K | 30K | 15K | 8K |
| 成本/天 | $0.40 | $0.10 | $0.05 | $0.03 |
| 节省 | - | 75% | 87.5% | 93% |

**最终成本**: $0.03/天 ≈ **$1/月** (10个币种)

---

## 实施建议

1. **立即**: 实施增量决策 (方案1)
2. **本周**: 压缩提示词 (方案2)
3. **下周**: 考虑分层决策 (方案3)
4. **按需**: 根据实际使用量调整模型 (方案4)
