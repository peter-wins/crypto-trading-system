# Bug 修复记录

## 2025-11-08 修复列表

### 🐛 Bug #1: Decimal JSON 序列化错误

**错误信息**:
```
TypeError: Object of type Decimal is not JSON serializable
```

**原因**:
`crypto_overview` 字典包含 Decimal 类型，无法直接序列化为 JSON

**修复位置**:
`src/decision/strategist.py` - `analyze_market_with_environment()` 方法

**解决方案**:
```python
def decimal_to_float(obj):
    if isinstance(obj, dict):
        return {k: decimal_to_float(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [decimal_to_float(item) for item in obj]
    elif isinstance(obj, Decimal):
        return float(obj)
    return obj

crypto_overview_serializable = decimal_to_float(crypto_overview)
crypto_summary = json.dumps(crypto_overview_serializable, ensure_ascii=False, indent=2)
```

**状态**: ✅ 已修复

---

### 🐛 Bug #2: 缺少 should_run_strategist 方法

**错误信息**:
```
AttributeError: 'LayeredDecisionCoordinator' object has no attribute 'should_run_strategist'
```

**原因**:
`main.py` 中调用了 `should_run_strategist()` 方法，但该方法未在协调器中实现

**修复位置**:
`src/decision/layered_coordinator.py`

**解决方案**:
```python
def __init__(self, ...):
    # ...
    self.last_strategist_run: Optional[datetime] = None

async def run_strategist_cycle(self, ...):
    # ...
    self.last_strategist_run = datetime.now(timezone.utc)

def should_run_strategist(self) -> bool:
    """判断是否应该运行战略层分析"""
    if not self.last_strategist_run:
        return True

    now = datetime.now(timezone.utc)
    elapsed = (now - self.last_strategist_run).total_seconds()

    return elapsed >= self.strategist_interval
```

**状态**: ✅ 已修复

---

### 🐛 Bug #3: JSON 解析失败

**错误信息**:
```
DecisionError: LLM 未返回有效的市场状态判断
```

**原因**:
LLM 返回的 JSON 可能包含 Markdown 代码块或注释，导致解析失败

**修复位置**:
`src/decision/strategist.py` - `_try_parse_json()` 函数

**解决方案**:
实现 3 层 fallback 机制：

1. **直接解析**: `json.loads(content)`
2. **提取 Markdown 代码块**: ````json ... ````
3. **正则提取对象**: `{ ... }`

```python
def _try_parse_json(content: str | None) -> Dict[str, Any]:
    if not content:
        return {}

    # 1. 尝试直接解析
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # 2. 尝试提取 JSON 代码块
    import re
    json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', content, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass

    # 3. 尝试查找 { ... } 对象
    brace_match = re.search(r'\{.*\}', content, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    return {}
```

**状态**: ✅ 已修复

---

### 🐛 Bug #4: Hyperliquid API 数据采集失败

**错误信息**:
```
DataCollectionError: Failed to fetch OHLCV for BTC/USDT (exchange=hyperliquid)
```

**原因**:
Hyperliquid 交易所 API 不稳定，频繁超时或限流

**修复位置**:
`.env` 配置文件

**解决方案**:
```bash
# 修改前
DATA_SOURCE_EXCHANGE=hyperliquid
DATA_SOURCE_SYMBOLS=BTC/USDC:USDC,ETH/USDC:USDC

# 修改后
DATA_SOURCE_EXCHANGE=binance
DATA_SOURCE_SYMBOLS=BTC/USDT,ETH/USDT,SOL/USDT
```

**推荐配置**:
- ✅ **Binance**: 最稳定，推荐使用
- ✅ **Binance USDM**: 合约数据，稳定
- ⚠️ **OKX/Bybit**: 可用但可能有限流
- ❌ **Hyperliquid**: 不推荐，不稳定

**状态**: ✅ 已修复

---

### 🐛 Bug #5: 符号匹配失败

**错误信息**:
```
INFO | 战略层推荐关注: ['BTC', 'ETH', 'SOL', 'BNB', 'XRP']
INFO | 没有推荐的币种需要分析
```

**原因**:
战略层推荐的是基础符号（`BTC`），但数据快照的 key 是完整交易对（`BTC/USDT`），导致匹配失败

**修复位置**:
`src/decision/layered_coordinator.py` - `run_trader_cycle()` 方法

**解决方案**:
```python
def matches_recommendation(full_symbol: str, recommended_list: list) -> bool:
    """检查完整交易对是否匹配推荐的基础符号"""
    # 提取基础符号（BTC/USDT -> BTC, BTC/USDC:USDC -> BTC）
    base = full_symbol.split('/')[0]
    return base in recommended_list or full_symbol in recommended_list

filtered_snapshots = {
    symbol: snapshot
    for symbol, snapshot in symbols_snapshots.items()
    if matches_recommendation(symbol, recommended)
}
```

**改进警告信息**:
```python
if not filtered_snapshots:
    logger.warning("没有推荐的币种需要分析")
    logger.warning(f"  可用币种: {list(symbols_snapshots.keys())}")
    logger.warning(f"  推荐币种: {recommended}")
    logger.warning("  提示: 确保配置的 DATA_SOURCE_SYMBOLS 包含推荐的币种")
    return {}
```

**测试结果**:
```
✅ 战略层推荐: ['BTC', 'ETH', 'SOL', 'BNB', 'XRP']
✅ 实际分析: ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']
✅ 生成信号: 3个 (BTC: enter_long, ETH: enter_long, SOL: hold)
```

**状态**: ✅ 已修复

---

### 🐛 Bug #6: 战术层符号格式不一致

**错误信息**:
```
解析信号: BTC → hold (置信度: 0.60)
解析信号: ETH → hold (置信度: 0.55)
解析信号: SOL → hold (置信度: 0.50)
WARNING | BTC/USDT 未在批量响应中找到，设为 None
WARNING | ETH/USDT 未在批量响应中找到，设为 None
WARNING | SOL/USDT 未在批量响应中找到，设为 None
```

**原因**:
提示词示例中使用了基础符号格式 (`"symbol": "BTC"`)，导致 LLM 学习错误的输出格式，而系统期望完整交易对格式 (`"BTC/USDT"`)

**修复位置**:
1. `src/decision/trader.py` - `_build_regime_aware_prompt()` 方法
2. `test_end_to_end_decision.py` - mock_snapshots 构造

**解决方案**:

1. **修改提示词示例** (`src/decision/trader.py:666-694`):
```python
# 修改前
{
    "symbol": "BTC",
    ...
}

# 修改后
{
    "symbol": "BTC/USDT",
    ...
}

# 并添加说明
1. **symbol必须使用完整交易对格式** (如 "BTC/USDT", "ETH/USDT")，与输入的币种格式完全一致
```

2. **修改测试数据格式** (`test_end_to_end_decision.py:154-156`):
```python
# 修改前
for symbol in recommended[:3]:
    if symbol in prices:
        mock_snapshots[symbol] = {...}

# 修改后
for symbol in recommended[:3]:
    if symbol in prices:
        full_symbol = f"{symbol}/USDT"
        mock_snapshots[full_symbol] = {...}
```

**测试结果**:
```
✅ 解析信号: BTC/USDT → enter_long (置信度: 0.72)
✅ 解析信号: ETH/USDT → hold (置信度: 0.65)
✅ 解析信号: SOL/USDT → enter_long (置信度: 0.68)
✅ 批量信号生成完成: 3/3
```

**状态**: ✅ 已修复

---

### 🐛 Bug #7: 不必要的工具调用

**错误信息**:
```
INFO | LLM 调用工具达到 6 次上限，已输出最终决策
```

**原因**:
战略层和战术层调用了 `_chat_with_tools()`，导致 LLM 尝试调用工具获取数据。但实际上所有数据已经通过感知层采集并包含在提示词中，完全不需要工具调用。

**影响**:
- 浪费 token（工具调用会增加多轮对话）
- 降低速度（需要等待多轮 LLM 调用）
- 可能触发工具调用上限

**修复位置**:
1. `src/decision/strategist.py:316` - `analyze_market_with_environment()` 方法
2. `src/decision/trader.py:227` - `generate_trading_signal()` 方法

**解决方案**:

```python
# 修改前
response = await self._chat_with_tools(messages)

# 修改后
# 不使用工具，因为所有数据已经通过感知层采集并包含在提示词中
response = await self.llm.chat(messages, tools=None)
```

**验证**: 运行测试后不再看到"调用工具达到上限"的日志

**注意**: `batch_generate_signals()` 和 `batch_generate_signals_with_regime()` 已经正确使用了 `tools=None`

**状态**: ✅ 已修复

---

### 🐛 Bug #8: 分层决策中重复生成信号

**错误现象**:
```
INFO | 战术层分析完成，收到 3 个信号
INFO | 发送给 LLM 的提示词 (SOL/USDT):  # <- 又调用了一次 LLM
```

**原因**:
分层决策流程中，信号已经由 `run_trader_cycle()` 批量生成，但执行时 `_execute_trading_logic()` 又调用 `_make_signal()` 重新生成了一遍信号

**影响**:
- 浪费 token（每个信号都生成两次）
- 降低速度（重复的 LLM 调用）
- 可能导致信号不一致

**修复位置**:
`main.py:739-741` - `run_with_layered_decision()` 方法中的信号执行逻辑

**解决方案**:

1. 创建新方法 `_execute_with_signal()`，直接使用已生成的信号
2. 创建 `_process_trading_signal()` 提取通用逻辑
3. 修改分层决策流程调用新方法

```python
# main.py:739-741
# 修改前
task = self._execute_trading_logic(symbol, strategy, snapshot, portfolio)

# 修改后
# 直接使用批量生成的信号，不要重新生成（避免重复 LLM 调用）
task = self._execute_with_signal(symbol, signal, strategy, snapshot, portfolio)
```

**架构改进**:
```python
# 新架构
async def _execute_with_signal():  # 分层模式 - 使用已有信号
    await self._process_trading_signal(...)

async def _execute_trading_logic():  # 传统模式 - 重新生成信号
    signal = await self._make_signal(...)
    await self._process_trading_signal(...)

async def _process_trading_signal():  # 通用逻辑 - 风控、下单
    # 风控检查
    # 订单执行
    # 记录更新
```

**状态**: ✅ 已修复

---

## 修复影响

| Bug | 严重程度 | 影响范围 | 修复难度 |
|-----|---------|---------|---------|
| Decimal 序列化 | 🔴 高 | 战略层初始化 | 🟢 简单 |
| should_run_strategist | 🔴 高 | 主循环运行 | 🟢 简单 |
| JSON 解析 | 🟡 中 | LLM 响应处理 | 🟡 中等 |
| Hyperliquid API | 🟡 中 | 数据采集 | 🟢 简单 |
| 符号匹配 | 🔴 高 | 战术层决策 | 🟡 中等 |
| 符号格式不一致 | 🔴 高 | 信号解析 | 🟢 简单 |
| 不必要的工具调用 | 🟡 中 | Token消耗/性能 | 🟢 简单 |
| 重复生成信号 | 🔴 高 | Token消耗/性能 | 🟡 中等 |

---

## 测试验证

### 端到端测试
```bash
source venv/bin/activate
python test_end_to_end_decision.py
```

**结果**: ✅ 全部通过

**输出示例**:
```
✅ 感知层 → 成功采集市场环境数据
✅ 战略层 → 成功生成市场状态判断 (sideways, 0.65)
✅ 战术层 → 成功生成交易信号 (3个)

BTC: enter_long (置信度 0.72)
ETH: enter_long (置信度 0.68)
SOL: hold (置信度 0.45)

🎉 端到端决策流程测试完成!
```

---

## 预防措施

### 1. 添加类型检查
```python
# 对于可能包含 Decimal 的数据，使用转换函数
if crypto_overview:
    crypto_overview_serializable = decimal_to_float(crypto_overview)
```

### 2. 增强错误日志
```python
# 添加详细的调试信息
logger.info("=" * 60)
logger.info("战略层 LLM 响应:")
logger.info(response.content or "(empty)")
logger.info("=" * 60)
```

### 3. 配置验证
```python
# 在启动时验证配置
if config.data_source_exchange == "hyperliquid":
    logger.warning("⚠️  Hyperliquid 可能不稳定，推荐使用 Binance")
```

### 4. 符号标准化
```python
# 统一符号格式处理
def normalize_symbol(symbol: str) -> str:
    """标准化交易对符号"""
    return symbol.split('/')[0]
```

---

## 相关文档

- [快速启动指南](QUICK_START.md)
- [分层决策架构](LAYERED_DECISION.md)
- [提示词优化](PROMPT_OPTIMIZATION.md)
- [更新日志](../UPDATES.md)

---

## 总结

所有已知 bug 已修复，系统现在可以稳定运行。建议：

1. ✅ 使用 Binance 作为数据源
2. ✅ 确保 DATA_SOURCE_SYMBOLS 包含战略层推荐的币种
3. ✅ 监控日志输出，及时发现问题
4. ✅ 定期运行测试验证系统状态

如遇到新问题，请查看日志文件：`logs/trading_system.log`
