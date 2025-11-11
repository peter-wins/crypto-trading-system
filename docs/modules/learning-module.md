# 学习模块开发指南

本文档提供学习模块的架构设计和开发要点。

## 1. 模块概述

学习模块是Agent自主进化的核心，负责：

```
交易结果
    ↓
绩效评估 → 识别问题/优势
    ↓
自我反思 → 生成改进建议
    ↓
策略优化 → 更新决策参数
    ↓
存储经验 → 下次决策时使用
```

核心理念：**从每次交易中学习，持续改进决策质量**

## 2. 绩效评估器设计

### 2.1 评估维度

**文件**: `src/learning/performance.py`

```python
class PerformanceEvaluator:
    """绩效评估器"""

    async def evaluate_trade()         # 单笔交易评估
    async def evaluate_period()        # 时间段评估
    async def compare_with_benchmark() # 基准比较
    async def analyze_trade_quality()  # 交易质量分析
```

### 2.2 单笔交易评估

```python
async def evaluate_trade(trade, entry_decision, exit_decision):
    """
    评估单笔交易

    评估指标:
    1. 盈亏金额和比例
    2. 持仓时间（是否过长/过短）
    3. 最大浮亏（是否触及风险底线）
    4. 退出方式（主动/止损/止盈）
    5. 与预期的偏差

    返回: {
        "pnl": Decimal,
        "pnl_percentage": Decimal,
        "holding_period": timedelta,
        "max_drawdown_during_trade": Decimal,
        "outcome": "success/failure",
        "exit_reason": "take_profit/stop_loss/manual/timeout",
        "quality_score": float,  # 0-100
        "analysis": str
    }
    """

    # 质量评分维度
    quality_score = 0

    # 1. 盈亏维度 (40分)
    if pnl > 0:
        quality_score += 40
    else:
        quality_score += max(0, 40 - abs(pnl_pct) * 10)

    # 2. 风险控制 (30分)
    if max_drawdown < stop_loss_threshold:
        quality_score += 30
    else:
        quality_score += max(0, 30 - (max_drawdown / stop_loss_threshold - 1) * 100)

    # 3. 执行效率 (30分)
    if holding_period within expected_range:
        quality_score += 30
    # ...
```

### 2.3 时间段评估

```python
async def evaluate_period(start_date, end_date):
    """
    评估时间段绩效

    计算指标（参考02-API-CONTRACTS.md）:
    - 收益指标: total_return, annualized_return
    - 风险指标: volatility, max_drawdown, sharpe_ratio
    - 交易指标: win_rate, profit_factor, avg_win/loss
    - 稳定性: max_consecutive_wins/losses

    分析维度:
    1. 横向对比: 与同期市场表现比较
    2. 纵向对比: 与历史表现比较
    3. 目标达成: 与设定目标比较
    4. 风险收益: 是否在合理范围内

    返回: PerformanceMetrics对象 + 分析报告
    """
```

### 2.4 基准比较

```python
async def compare_with_benchmark(benchmark_symbol="BTC/USDT"):
    """
    与基准(如BTC)比较

    计算指标:
    - Alpha: 超额收益 = 策略收益 - 基准收益
    - Beta: 系统性风险 = Cov(策略,基准) / Var(基准)
    - Correlation: 与基准相关性
    - Information Ratio: Alpha / Tracking Error

    分析:
    - Alpha > 0: 跑赢基准
    - Beta < 1: 风险低于市场
    - Correlation < 0.7: 策略有独立性

    参考: 量化投资经典指标
    """
```

## 3. 反思引擎设计

### 3.1 反思层次

**文件**: `src/learning/reflection.py`

```python
class LLMReflectionEngine:
    """基于LLM的反思引擎"""

    async def reflect_on_trade()      # 交易级反思
    async def reflect_on_period()     # 阶段性反思
    async def identify_patterns()     # 模式识别
    async def meta_reflection()       # 元反思（反思决策流程本身）
```

### 3.2 交易反思Prompt

```python
trade_reflection_prompt = """
请对以下交易进行深入反思：

交易信息：
- 币种: {symbol}
- 方向: {side}
- 入场价格: {entry_price}
- 出场价格: {exit_price}
- 持仓时间: {holding_period}
- 盈亏: {pnl} ({pnl_percentage}%)

决策过程：
- 入场理由: {entry_reasoning}
- 当时市场状态: {market_context}
- 使用的指标: {indicators}

结果：
- 最终结果: {outcome}
- 退出原因: {exit_reason}
- 期间最大浮亏: {max_drawdown}

请回答：
1. 这个决策的优点是什么？哪些做对了？
2. 有哪些可以改进的地方？
3. 如果重新来过，你会如何调整？
4. 从中学到了什么经验教训（3-5条）？
5. 这次经验对未来决策有什么启示？

请客观、深入地分析，既不要过度自责也不要盲目自信。
"""
```

### 3.3 阶段性反思

```python
period_reflection_prompt = """
请对过去{period}天的交易表现进行总体反思：

绩效数据：
- 总收益: {total_return}%
- 夏普比率: {sharpe_ratio}
- 最大回撤: {max_drawdown}%
- 胜率: {win_rate}%
- 总交易次数: {total_trades}

市场环境：
- 市场趋势: {market_trend}
- 波动率: {volatility}
- 主要事件: {major_events}

请分析：
1. 整体表现总结（成绩、问题）
2. 优势：哪些做得好？为什么？
3. 劣势：哪些需要改进？根本原因是什么？
4. 市场适应性：策略是否适应当前市场？
5. 改进计划：下一阶段具体改进措施（3-5项）

请提供可操作的改进建议，而不只是笼统的建议。
"""
```

### 3.4 模式识别

```python
async def identify_patterns(experiences: List[TradingExperience]):
    """
    识别交易模式

    分析维度:
    1. 成功模式
       - 什么情况下胜率高？
       - 哪些指标组合效果好？
       - 最佳入场时机？

    2. 失败模式
       - 什么情况下容易亏损？
       - 哪些信号不可靠？
       - 常见的错误决策？

    3. 行为偏差
       - 是否存在过度交易？
       - 止损是否过早/过晚？
       - 是否追涨杀跌？

    使用方法:
    - 聚类分析：相似交易分组
    - 统计分析：不同条件下的表现
    - LLM分析：深层模式识别

    返回: [
        {
            "pattern": "超卖反弹",
            "frequency": 15,
            "success_rate": 73.3%,
            "description": "RSI<30时入场，24h内反弹",
            "recommendation": "继续使用，但加入趋势确认"
        },
        ...
    ]
    """
```

## 4. 策略优化器设计

### 4.1 优化策略

**文件**: `src/learning/optimizer.py`

```python
class StrategyOptimizer:
    """策略优化器"""

    async def optimize_parameters()      # 参数优化
    async def evaluate_strategy()        # 策略评估
    async def a_b_testing()             # A/B测试
    async def auto_adjust_risk_params() # 自动调整风险参数
```

### 4.2 参数优化方法

```python
# 方法1: 网格搜索
params_grid = {
    "rsi_oversold": [20, 25, 30],
    "rsi_overbought": [70, 75, 80],
    "stop_loss_pct": [3, 5, 7]
}
best_params = grid_search(params_grid, historical_data)

# 方法2: 贝叶斯优化
from skopt import gp_minimize
best_params = gp_minimize(
    objective_function,
    param_space,
    n_calls=50
)

# 方法3: 遗传算法
from deap import algorithms
best_params = genetic_algorithm(
    population_size=100,
    generations=50
)

# 方法4: LLM建议
llm_suggestion = await llm.chat([
    Message(role="system", content="你是策略优化专家"),
    Message(role="user", content=f"""
        当前参数: {current_params}
        最近表现: {recent_performance}
        请建议参数调整
    """)
])
```

### 4.3 自动风险调整

```python
async def auto_adjust_risk_params(performance: PerformanceMetrics):
    """
    根据表现自动调整风险参数

    策略:
    1. 连续盈利 → 适度增加风险敞口
       if consecutive_wins > 5 and sharpe > 2.0:
           max_position_size *= 1.1  # 增加10%
           但不超过绝对上限(30%)

    2. 连续亏损 → 降低风险敞口
       if consecutive_losses > 3:
           max_position_size *= 0.8  # 减少20%

    3. 高波动期 → 降低仓位
       if recent_volatility > historical_avg * 1.5:
           reduce_position_size()

    4. 回撤接近限制 → 保守模式
       if drawdown > max_drawdown * 0.8:
           max_position_size *= 0.5
           enable_conservative_mode()

    记录所有调整到数据库，供后续分析
    """
```

## 5. 学习循环集成

### 5.1 完整学习流程

```python
async def learning_loop():
    """
    自主学习循环（每日运行）

    1. 收集昨日数据
       trades = await db.get_trades(yesterday)
       decisions = await db.get_decisions(yesterday)

    2. 评估绩效
       performance = await evaluator.evaluate_period(yesterday)

    3. 单笔交易反思
       for trade in trades:
           reflection = await reflector.reflect_on_trade(trade)
           experience = create_experience(trade, reflection)
           await memory.store_experience(experience)

    4. 整体反思
       period_reflection = await reflector.reflect_on_period(performance)

    5. 模式识别
       recent_exp = await memory.get_recent_experiences(30_days)
       patterns = await reflector.identify_patterns(recent_exp)

    6. 策略调整（如需要）
       if should_adjust_strategy(performance, patterns):
           new_params = await optimizer.optimize_parameters()
           await update_strategy(new_params, reason=period_reflection)

    7. 生成学习报告
       report = generate_learning_report(performance, reflection, patterns)
       await send_report(report)
    """
```

### 5.2 触发条件

```python
# 什么时候触发学习？
1. 每日定时: 00:00 UTC（回顾昨日）
2. 每周定时: 周日总结周表现
3. 重大事件:
   - 触发熔断后
   - 单笔亏损>5%后
   - 连续3笔亏损后
4. 里程碑:
   - 累计交易100笔
   - 运行满1个月
```

## 6. 元学习机制

### 6.1 学习如何学习

```python
# 元反思：反思学习过程本身
meta_reflection_prompt = """
请反思过去{period}的学习效果：

学习记录：
- 进行了{num_reflections}次反思
- 识别了{num_patterns}个模式
- 调整策略{num_adjustments}次

效果评估：
- 调整前后收益对比
- 识别的模式是否有效
- 反思建议是否被采纳

请分析：
1. 学习过程是否有效？哪些环节有用？
2. 反思质量如何？是否足够深入？
3. 从失败中的学习是否充分？
4. 模式识别的准确性如何？
5. 如何改进学习过程本身？

这是对"学习能力"本身的学习和优化。
"""
```

### 6.2 知识迁移

```python
# 跨市场学习
如何将BTC的交易经验应用到ETH？

1. 提取通用模式
   - 超买超卖的反转模式
   - 趋势跟随策略
   - 风险管理原则

2. 识别差异
   - ETH波动率更高
   - 与BTC相关性0.8
   - 受DeFi生态影响

3. 调整应用
   - 保持核心逻辑
   - 调整参数(ETH需要更宽的止损)
   - 增加特定指标(ETH/BTC比率)
```

## 7. 接口定义

**参考**: `docs/prd/02-API-CONTRACTS.md` 第6章

所有接口已在API契约文档中定义。

## 8. 实验和测试

### 8.1 回测验证

```python
# 验证学习效果
1. 基线测试: 未学习的原始策略表现
2. 学习后测试: 应用学习改进后的表现
3. 对比分析: 学习是否真的有效？

指标:
- 收益提升
- 风险降低
- 稳定性提高
```

### 8.2 A/B测试

```python
# 在实盘中小规模测试新策略
- A组: 50%资金，使用当前策略
- B组: 50%资金，使用优化后策略
- 运行2周后比较表现
- 选择更好的策略全量部署
```

## 9. 监控指标

```python
学习效果指标:
- 平均反思质量分数（人工评分）
- 识别模式的准确率
- 策略调整后的收益变化
- 学习-应用的时间延迟
- 经验库增长速度和质量
```

## 10. 开发顺序建议

```
1. 实现绩效评估器                    - 3小时
2. 实现反思引擎（LLM集成）          - 4小时
3. 实现模式识别                      - 3小时
4. 实现策略优化器                    - 4小时
5. 集成学习循环                      - 2小时
6. 测试和调优                        - 4小时
```

## 11. 常见问题

**Q: 如何避免过拟合？**
A: 1) 使用walk-forward测试 2) 保留验证集 3) 限制参数调整频率 4) 简单优于复杂

**Q: LLM反思会不会产生幻觉？**
A: 1) Prompt中强调客观性 2) 结合量化指标验证 3) 人工审核关键反思 4) 多次反思交叉验证

**Q: 学习频率多高合适？**
A: 初期：每日学习。成熟后：每周学习。避免过度调整导致策略不稳定。

**Q: 如何平衡探索和利用？**
A: Epsilon-greedy策略：90%时间用最佳策略，10%时间尝试新策略。

## 12. 伦理和风险

```python
学习系统的风险:
1. 自我强化错误模式
   - 缓解: 定期人工审核，硬编码安全边界

2. 过度优化导致脆弱性
   - 缓解: 注重鲁棒性而非极致性能

3. 黑盒决策难以解释
   - 缓解: 详细记录所有决策和理由

4. 市场regime突变时失效
   - 缓解: 保持保守，快速熔断机制
```

## 13. 参考资料

- Reinforcement Learning经典论文
- AutoML和超参数优化
- LangChain的Agent机制
- AlphaGo的自我对弈学习
