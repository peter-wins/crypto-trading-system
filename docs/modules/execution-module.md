# 执行模块开发指南

本文档提供执行模块的架构设计和开发要点。

## 1. 模块概述

执行模块负责将决策转化为实际交易，包括：

```
决策信号
    ↓
风险检查 → [PASS] → 订单创建 → 订单监控
    ↓                     ↓             ↓
  [FAIL]            订单管理       仓位管理
    ↓                     ↓             ↓
  拒绝            止损/止盈      组合同步
```

核心原则：**安全第一，宁可错过机会，也不冒不可控风险**

## 2. 订单执行器设计

### 2.1 架构设计

**文件**: `src/execution/order.py`

**核心类**:
```python
class CCXTOrderExecutor:
    """基于CCXT的订单执行器"""

    async def create_order(symbol, side, type, amount, price, **kwargs)
    async def cancel_order(order_id, symbol)
    async def get_order(order_id, symbol)
    async def get_open_orders(symbol=None)
    async def modify_order(order_id, updates)  # 修改订单
```

### 2.2 订单类型支持

```python
支持的订单类型:
- MARKET: 市价单（立即成交）
- LIMIT: 限价单（指定价格）
- STOP_LOSS: 止损单
- STOP_LOSS_LIMIT: 止损限价单
- TAKE_PROFIT: 止盈单
- TAKE_PROFIT_LIMIT: 止盈限价单

# 使用场景
1. 进场: LIMIT订单（更好的价格）
2. 止损: STOP_LOSS（保护资金）
3. 止盈: TAKE_PROFIT（锁定利润）
4. 紧急出场: MARKET订单（快速成交）
```

### 2.3 订单生命周期管理

```python
创建订单
    ↓
pending → open → partially_filled → filled
              ↓           ↓
           canceled    canceled
              ↓
          rejected/expired

# 状态监控
- 每30秒查询一次open订单状态
- 超过5分钟未成交的限价单考虑取消
- 记录所有状态变化到数据库
```

### 2.4 执行优化

```python
# 智能订单路由
1. 检查订单簿流动性
2. 评估市场冲击成本
3. 大单拆分（避免影响价格）
4. 时间加权执行（TWAP）

# 滑点控制
- 限价单: 设置可接受的滑点范围
- 市价单: 提前估算滑点
- 超过阈值: 放弃执行或调整数量
```

## 3. 风险管理器设计

### 3.1 多层风险检查

**文件**: `src/execution/risk.py`

```python
class StandardRiskManager:
    """标准风险管理器"""

    # 三层检查
    async def check_order_risk()      # 订单级风险
    async def check_position_risk()   # 持仓级风险
    async def check_portfolio_risk()  # 组合级风险
```

### 3.2 风险检查清单

#### 订单级检查

```python
def check_order_risk(signal, portfolio, risk_params):
    """
    订单风险检查

    检查项:
    1. 仓位大小限制
       - 单笔不超过总资产的 max_single_trade
       - 单币种不超过 max_position_size

    2. 资金充足性
       - 可用余额 >= 订单所需资金
       - 保留emergency_reserve（5%）不动用

    3. 杠杆限制
       - 不使用杠杆（初期）
       - 或最多2倍杠杆

    4. 价格合理性
       - 限价单价格偏离市价不超过5%
       - 止损价格合理（不能高于入场价）

    返回: RiskCheckResult(passed=True/False, reason=None)
    """
```

#### 持仓级检查

```python
def check_position_risk(position, current_price):
    """
    持仓风险检查

    检查项:
    1. 止损触发
       - 亏损 >= stop_loss_percentage → 平仓

    2. 止盈触发
       - 盈利 >= take_profit_percentage → 平仓

    3. 移动止损
       - 盈利>10%后，止损价移到成本价
       - 盈利>20%后，止损价移到+10%

    4. 持仓时间
       - 超过max_holding_period → 考虑平仓
    """
```

#### 组合级检查

```python
def check_portfolio_risk(portfolio):
    """
    组合风险检查

    检查项:
    1. 日亏损限制
       - daily_loss >= max_daily_loss → 熔断

    2. 总回撤限制
       - drawdown >= max_drawdown → 减仓

    3. 持仓集中度
       - 单币种仓位 <= max_position_size
       - 最多持有 max_open_positions 个币种

    4. 波动率监控
       - 组合波动率 > threshold → 降低仓位

    返回: RiskCheckResult + 建议动作
    """
```

### 3.3 熔断机制

```python
# 触发熔断的情况
1. 日亏损达到限制 → 停止交易24小时
2. 系统异常错误 → 全部平仓，停止交易
3. 交易所连接失败 → 暂停新单，监控持仓
4. 极端市场波动 → 降低仓位到安全水平

# 熔断后恢复
- 记录熔断原因和时间
- 人工审核后才能恢复
- 或自动在next_day 00:00恢复
```

### 3.4 止损止盈计算

```python
def calculate_stop_loss_take_profit(entry_price, side, risk_params):
    """
    计算止损止盈价格

    止损策略:
    - ATR止损: stop_loss = entry_price ± (ATR × multiplier)
    - 百分比止损: stop_loss = entry_price × (1 ± stop_loss_pct)
    - 支撑阻力止损: 基于技术分析

    止盈策略:
    - 风险回报比: take_profit距离 = stop_loss距离 × risk_reward_ratio
    - 默认 risk_reward_ratio = 2 (盈亏比1:2)

    返回: {
        "stop_loss": Decimal,
        "take_profit": Decimal,
        "risk_amount": Decimal
    }
    """
```

## 4. 投资组合管理器设计

### 4.1 核心职责

**文件**: `src/execution/portfolio.py`

```python
class PortfolioManager:
    """投资组合管理器"""

    # 核心功能
    async def get_current_portfolio()    # 获取当前组合
    async def update_portfolio()         # 同步交易所状态
    async def get_position(symbol)       # 获取持仓
    async def calculate_metrics()        # 计算绩效指标
```

### 4.2 组合同步策略

```python
# 同步频率
- 实时: 每次交易后立即同步
- 定期: 每5分钟同步一次
- 完整: 每日收盘后完整同步

# 同步内容
1. 账户余额（现金、冻结、总额）
2. 持仓明细（数量、成本、当前价）
3. 未完成订单
4. 最新成交记录

# 数据一致性
- 对比本地记录与交易所数据
- 发现差异时记录warn日志
- 以交易所数据为准（真实来源）
```

### 4.3 仓位计算

```python
def calculate_position_size(signal, portfolio, risk_params):
    """
    计算合理的仓位大小

    方法1: 固定比例法
    position_size = total_value × position_pct

    方法2: 固定风险法（推荐）
    risk_amount = total_value × max_daily_loss / max_positions
    position_size = risk_amount / (entry_price - stop_loss_price)

    方法3: 凯利公式
    kelly_pct = (win_rate × avg_win - loss_rate × avg_loss) / avg_win
    position_size = total_value × kelly_pct × kelly_fraction

    限制:
    - position_size <= total_value × max_position_size
    - position_size <= max_single_trade
    - position_size >= min_order_size (交易所限制)
    """
```

### 4.4 绩效计算

```python
async def calculate_metrics(start_date, end_date):
    """
    计算投资组合绩效指标

    收益指标:
    - total_return: 总收益率
    - annualized_return: 年化收益率
    - daily_returns: 每日收益序列

    风险指标:
    - volatility: 收益波动率（标准差）
    - max_drawdown: 最大回撤
    - sharpe_ratio: 夏普比率 = (收益-无风险利率) / 波动率
    - sortino_ratio: 索提诺比率（只考虑下行波动）
    - calmar_ratio: 卡尔玛比率 = 年化收益 / 最大回撤

    交易指标:
    - total_trades: 总交易次数
    - win_rate: 胜率
    - profit_factor: 盈亏比 = 总盈利 / 总亏损
    - avg_win, avg_loss: 平均盈利/亏损

    参考: docs/prd/01-DATA-MODELS.md 第7章
    """
```

## 5. 交易执行流程

### 5.1 完整流程

```python
async def execute_trading_signal(signal: TradingSignal):
    """
    执行交易信号的完整流程

    1. 获取当前组合状态
       portfolio = await portfolio_manager.get_current_portfolio()

    2. 风险检查
       risk_check = await risk_manager.check_order_risk(
           signal, portfolio, risk_params
       )
       if not risk_check.passed:
           logger.warning(f"Risk check failed: {risk_check.reason}")
           return None

    3. 计算仓位大小
       position_size = calculate_position_size(signal, portfolio, risk_params)

    4. 计算止损止盈
       sl_tp = calculate_stop_loss_take_profit(
           signal.suggested_price, signal.side, risk_params
       )

    5. 创建订单
       order = await order_executor.create_order(
           symbol=signal.symbol,
           side=signal.side,
           type="limit",
           amount=position_size,
           price=signal.suggested_price,
           stop_loss=sl_tp["stop_loss"],
           take_profit=sl_tp["take_profit"]
       )

    6. 记录决策
       await db.save_decision_record(signal, order, risk_check)

    7. 监控订单
       asyncio.create_task(monitor_order(order.id))

    8. 更新组合
       await portfolio_manager.update_portfolio()

    返回: order
    """
```

### 5.2 订单监控

```python
async def monitor_order(order_id):
    """
    持续监控订单直到完成

    1. 定期查询订单状态（每30秒）
    2. 如果partially_filled，评估是否取消剩余部分
    3. 如果长时间未成交，考虑修改价格
    4. 状态变化时发送通知
    5. 订单完成后更新持仓信息
    """
```

## 6. 安全机制

### 6.1 多重安全保护

```python
1. 配置级保护
   - enable_trading开关（默认false）
   - testnet模式强制开启

2. 代码级保护
   - 所有订单前进行风险检查
   - Double check（确认两次）
   - 订单金额上限硬编码

3. 运行时保护
   - 熔断机制自动触发
   - 异常情况自动平仓
   - 人工干预接口

4. 监控告警
   - 大额订单告警
   - 频繁交易告警
   - 异常亏损告警
```

### 6.2 API权限控制

```python
# 交易所API权限设置
✅ 允许: 读取账户信息
✅ 允许: 读取订单信息
✅ 允许: 创建订单
✅ 允许: 取消订单
❌ 禁止: 提现（Withdraw）
❌ 禁止: 内部转账
❌ 禁止: 杠杆交易（初期）

# IP白名单
只允许特定IP访问交易所API
```

## 7. 接口定义

**参考**: `docs/prd/02-API-CONTRACTS.md` 第5章

所有接口已在API契约文档中定义，实现时严格遵守。

## 8. 测试策略

### 8.1 单元测试

```python
# tests/execution/test_order.py
- Mock交易所响应测试订单创建
- 测试各种订单类型
- 测试错误处理和重试

# tests/execution/test_risk.py
- 测试各级风险检查
- 测试熔断触发条件
- 测试止损止盈计算

# tests/execution/test_portfolio.py
- 测试组合同步
- 测试仓位计算
- 测试绩效指标计算
```

### 8.2 集成测试

```python
# 使用Testnet进行完整流程测试
1. 连接到testnet
2. 执行小额测试订单
3. 验证订单状态变化
4. 验证组合同步正确
5. 测试熔断机制
```

### 8.3 模拟测试

```python
# 历史数据回测
1. 加载历史K线数据
2. 模拟生成交易信号
3. 模拟订单执行（考虑滑点）
4. 计算模拟收益和风险指标
5. 验证策略有效性
```

## 9. 监控指标

```python
关键指标:
- 订单成功率
- 平均成交时间
- 滑点统计（实际成交价 vs 期望价格）
- 拒单率（风险检查未通过）
- API延迟（P50, P95, P99）
- 熔断触发次数
- 持仓价值和分布
```

## 10. 开发顺序建议

```
1. 实现订单执行器（CCXTOrderExecutor）      - 4小时
2. 实现风险管理器（StandardRiskManager）    - 4小时
3. 实现组合管理器（PortfolioManager）       - 3小时
4. 集成测试（Testnet）                      - 3小时
5. 监控和告警                                - 2小时
```

## 11. 常见问题

**Q: 如何处理部分成交？**
A: 1) 小额订单：等待完全成交 2) 大额订单：接受部分成交，剩余取消

**Q: 滑点太大怎么办？**
A: 1) 使用限价单而非市价单 2) 拆分大单 3) 选择流动性好的交易对

**Q: 如何保证资金安全？**
A: 1) API只读权限 + 交易权限（禁提现） 2) IP白名单 3) 多层风险检查 4) 熔断机制

**Q: 交易所宕机怎么办？**
A: 1) 使用多个交易所分散风险 2) 保持持仓信息本地副本 3) 宕机期间禁止新单 4) 恢复后同步状态

## 12. 参考资料

- CCXT文档
- 各交易所API文档
- 风险管理最佳实践
- 算法交易策略
