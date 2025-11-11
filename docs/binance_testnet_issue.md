# Binance 测试网问题说明

## 问题描述

在运行系统时发现**止损止盈订单日志显示"已设置"，但实际在币安测试网界面看不到订单**。

## 根本原因

### CCXT 库错误信息

```
ccxt.base.errors.NotSupported: binanceusdm testnet/sandbox mode is not supported for futures anymore,
please check the deprecation announcement https://t.me/ccxt_announcements/92 and consider using the demo trading instead.
```

### 核心问题

**Binance USDT 永续合约的测试网已经被废弃**

- 币安官方在 2024年 停止了 USDT 永续合约测试网服务
- CCXT 库从某个版本开始不再支持 `testnet=True` 用于永续合约
- 现在有两种替代方案：
  1. **Demo Trading（模拟交易）** - 币安新推出的模拟交易功能
  2. **Paper Trading（纸面交易）** - 本地模拟，不与交易所交互

## 当前配置

```.env
BINANCE_TESTNET=true       # ← 永续合约测试网已废弃！
BINANCE_FUTURES=true       # ← 使用 USDT 永续合约
ENABLE_TRADING=true        # ← 启用交易
```

这个配置会导致：
- ✅ 可以拉取市场数据（公开API）
- ✅ 可以创建主订单（可能实际没提交）
- ❌ 止损止盈订单可能创建失败（但错误被捕获了）
- ❌ 无法查询持仓和未完成订单

## 解决方案

### 方案 1：使用币安现货测试网（推荐用于测试）

**优点：** 完全免费，不会用真钱
**缺点：** 只能测试现货交易，无法测试永续合约

**配置：**
```.env
BINANCE_TESTNET=true
BINANCE_FUTURES=false      # 改为 false，使用现货
ENABLE_TRADING=true
```

**适用场景：**
- 测试系统基本功能
- 验证订单逻辑
- 调试代码

---

### 方案 2：使用纸面交易模式（推荐用于开发）

**优点：** 完全本地模拟，速度快，不依赖交易所
**缺点：** 无法测试真实交易所的响应和错误

**配置：**
```.env
BINANCE_TESTNET=false      # 可以连接主网拉数据
BINANCE_FUTURES=true       # 永续合约
ENABLE_TRADING=false       # ← 纸面交易，不真实下单
```

**系统行为：**
- ✅ 从主网拉取真实市场数据
- ✅ LLM 基于真实数据做决策
- ✅ 本地模拟订单执行
- ❌ 不会向交易所发送真实订单
- ✅ 本地维护模拟持仓和余额

---

### 方案 3：使用主网小资金测试（谨慎！）

**优点：** 测试真实交易流程
**缺点：** **会用真钱，有亏损风险！**

**配置：**
```.env
BINANCE_TESTNET=false      # 主网
BINANCE_FUTURES=true       # 永续合约
ENABLE_TRADING=true        # 真实交易
```

**⚠️ 风险警告：**
- 使用真实资金
- 可能因为bug导致亏损
- 建议只用极小金额测试（如 10 USDT）
- 设置严格的风控参数

**风控配置：**
```.env
MAX_POSITION_SIZE=0.01     # 每笔最多1%资金
MAX_DAILY_LOSS=0.02        # 每日最多亏损2%
MAX_DRAWDOWN=0.05          # 最大回撤5%
```

---

### 方案 4：使用币安 Demo Trading（未实现）

**币安新的模拟交易功能，但需要：**
1. 注册 Demo 账户
2. 获取 Demo API Key
3. 使用特定的 API endpoint

**CCXT 支持情况：** 需要检查最新版本是否支持

---

## 推荐配置（分阶段）

### 阶段 1：开发调试
```env
BINANCE_TESTNET=false
BINANCE_FUTURES=true
ENABLE_TRADING=false  # 纸面交易
```

### 阶段 2：功能测试
```env
BINANCE_TESTNET=true
BINANCE_FUTURES=false  # 现货测试网
ENABLE_TRADING=true
```

### 阶段 3：小资金实盘
```env
BINANCE_TESTNET=false
BINANCE_FUTURES=true
ENABLE_TRADING=true
MAX_POSITION_SIZE=0.01
MAX_SINGLE_TRADE=10  # 每笔最多 10 USDT
```

### 阶段 4：正式运行
```env
BINANCE_TESTNET=false
BINANCE_FUTURES=true
ENABLE_TRADING=true
MAX_POSITION_SIZE=0.2  # 恢复正常参数
```

---

## 止损止盈订单问题总结

### 为什么日志显示"已设置"但看不到订单？

1. **测试网废弃** - 永续合约测试网不再可用
2. **错误被捕获** - 代码中 `except Exception` 捕获了创建失败的异常
3. **日志误导** - 在异常捕获前就打印了"已设置"日志

### 修复方案

#### 方案 A：改进日志（已完成）

```python
# 修改前
logger.info("✓ 止损订单已设置：%s", symbol)

# 修改后
logger.info("✓ 止损订单已设置：%s, 订单ID: %s", symbol, stop_order.id)
logger.error("❌ 止损订单创建失败: %s", exc, exc_info=True)
```

#### 方案 B：使用纸面交易模式

设置 `ENABLE_TRADING=false`，系统会：
- ✅ 创建模拟止损止盈订单
- ✅ 在本地存储和管理
- ✅ 模拟触发和执行

#### 方案 C：切换到现货测试网

设置 `BINANCE_FUTURES=false`：
- ✅ 现货测试网仍然可用
- ✅ 可以真实测试订单创建
- ❌ 无法测试永续合约特性

---

## 验证止损止盈是否生效

### 方法 1：查看详细日志

```bash
tail -f logs/trading_system.log | grep "止损\|止盈\|订单ID"
```

如果看到"订单ID: xxx"，说明创建成功

### 方法 2：检查数据库

```sql
SELECT * FROM orders WHERE order_type IN ('stop_loss', 'take_profit');
```

### 方法 3：查询交易所API

使用 `scripts/check_binance_orders.py`（需要先修复测试网问题）

---

## 总结

| 方案 | 成本 | 真实性 | 推荐用途 |
|------|------|--------|----------|
| 纸面交易 | 免费 | ⭐⭐ | 开发调试 |
| 现货测试网 | 免费 | ⭐⭐⭐ | 功能测试 |
| 主网小资金 | 小额 | ⭐⭐⭐⭐⭐ | 实盘验证 |
| Demo Trading | 免费 | ⭐⭐⭐⭐ | 待实现 |

**当前推荐：使用纸面交易模式（`ENABLE_TRADING=false`）**

这样可以：
- 拉取真实市场数据
- 测试完整的交易逻辑
- 完全没有资金风险
- 可以看到所有订单创建过程

---

**更新时间**: 2025-11-08
**问题来源**: Binance 废弃了 USDT 永续合约测试网
**相关链接**: https://t.me/ccxt_announcements/92
