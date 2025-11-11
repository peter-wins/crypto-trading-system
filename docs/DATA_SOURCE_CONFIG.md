# 数据源配置完整指南

## 🎯 配置概览

本系统支持**数据源与交易所分离**的架构：

```
┌─────────────────────┐
│  数据源 (拉数据)      │ ← 配置在 .env 的 DATA_SOURCE_*
│  不需要 API Key      │
└─────────────────────┘
         ↓
    缓存到 Redis
         ↓
┌─────────────────────┐
│  交易所 (下单)       │ ← 配置在 .env 的 BINANCE_*/OKX_*
│  需要 API Key       │
└─────────────────────┘
```

---

## 📝 配置文件 (.env)

### 1. 数据源配置（必填）

```bash
# 数据源交易所
DATA_SOURCE_EXCHANGE=hyperliquid

# 监控的交易对（逗号分隔，格式需匹配数据源）
DATA_SOURCE_SYMBOLS=BTC/USDC:USDC,ETH/USDC:USDC

# 数据采集间隔（秒）
DATA_COLLECTION_INTERVAL=3
```

### 2. 交易所配置（可选，仅交易时需要）

```bash
# Binance（用于下单）
BINANCE_API_KEY=your_key_here
BINANCE_API_SECRET=your_secret_here
BINANCE_TESTNET=true
BINANCE_FUTURES=true
```

---

## 🔧 支持的数据源

### Hyperliquid（推荐）

**特点：**
- ✅ 免费、无需 API Key
- ✅ 实时数据质量高
- ✅ 永续合约数据

**配置：**
```bash
DATA_SOURCE_EXCHANGE=hyperliquid
DATA_SOURCE_SYMBOLS=BTC/USDC:USDC,ETH/USDC:USDC,SOL/USDC:USDC
```

**交易对格式：** `BASE/USDC:USDC`

---

### Binance 现货

**配置：**
```bash
DATA_SOURCE_EXCHANGE=binance
DATA_SOURCE_SYMBOLS=BTC/USDT,ETH/USDT,SOL/USDT
```

**交易对格式：** `BASE/USDT`

---

### Binance USDT 永续合约

**配置：**
```bash
DATA_SOURCE_EXCHANGE=binanceusdm
DATA_SOURCE_SYMBOLS=BTC/USDT,ETH/USDT,SOL/USDT
```

**交易对格式：** `BASE/USDT`

---

### OKX

**配置：**
```bash
DATA_SOURCE_EXCHANGE=okx
DATA_SOURCE_SYMBOLS=BTC/USDT:USDT,ETH/USDT:USDT,SOL/USDT:USDT
```

**交易对格式：** `BASE/USDT:USDT`（永续合约）

---

### Bybit

**配置：**
```bash
DATA_SOURCE_EXCHANGE=bybit
DATA_SOURCE_SYMBOLS=BTC/USDT:USDT,ETH/USDT:USDT
```

**交易对格式：** `BASE/USDT:USDT`

---

## 📊 交易对格式对照表

| 交易所 | 现货格式 | 永续合约格式 |
|--------|---------|------------|
| Hyperliquid | 不支持 | `BTC/USDC:USDC` |
| Binance | `BTC/USDT` | `BTC/USDT` (binanceusdm) |
| OKX | `BTC/USDT` | `BTC/USDT:USDT` |
| Bybit | `BTC/USDT` | `BTC/USDT:USDT` |

---

## 🚀 快速配置示例

### 示例 1：从 Hyperliquid 拉数据 + 在 Binance 交易

**.env 配置：**
```bash
# 数据源：Hyperliquid（免费）
DATA_SOURCE_EXCHANGE=hyperliquid
DATA_SOURCE_SYMBOLS=BTC/USDC:USDC,ETH/USDC:USDC
DATA_COLLECTION_INTERVAL=3

# 交易所：Binance（需要 Key）
BINANCE_API_KEY=your_key
BINANCE_API_SECRET=your_secret
BINANCE_TESTNET=true
BINANCE_FUTURES=true
```

**好处：**
- Hyperliquid 数据免费、质量高
- Binance 账户用于交易
- 数据与交易完全分离

---

### 示例 2：全部使用 Binance

**.env 配置：**
```bash
# 数据源：Binance
DATA_SOURCE_EXCHANGE=binanceusdm
DATA_SOURCE_SYMBOLS=BTC/USDT,ETH/USDT
DATA_COLLECTION_INTERVAL=3

# 交易所：Binance（同一个）
BINANCE_API_KEY=your_key
BINANCE_API_SECRET=your_secret
BINANCE_TESTNET=true
BINANCE_FUTURES=true
```

---

## ✅ 验证配置

启动系统后，查看日志：

```bash
python main.py
```

**正确的日志输出：**
```
运行环境: dev
数据源: hyperliquid
数据采集间隔: 3秒
决策循环间隔: 60秒
监控交易对: BTC/USDC:USDC, ETH/USDC:USDC
📊 数据源: hyperliquid
💰 交易所: binanceusdm
Initialized hyperliquid market data collector
✅ 后台数据采集任务已启动（每 3 秒更新）
```

---

## ⚠️ 常见问题

### 1. 交易对格式错误

**错误示例：**
```bash
# Hyperliquid 使用了 Binance 格式
DATA_SOURCE_EXCHANGE=hyperliquid
DATA_SOURCE_SYMBOLS=BTC/USDT  # ❌ 错误
```

**正确配置：**
```bash
DATA_SOURCE_EXCHANGE=hyperliquid
DATA_SOURCE_SYMBOLS=BTC/USDC:USDC  # ✅ 正确
```

---

### 2. 数据源不需要 API Key

**错误理解：**
> "我想用 Hyperliquid，需要配置 HYPERLIQUID_API_KEY"

**正确理解：**
- 拉取**公开数据**不需要 API Key
- 只有**交易**才需要 API Key

---

### 3. 切换数据源

只需修改 `.env` 的 `DATA_SOURCE_EXCHANGE`：

```bash
# 从 Hyperliquid 切换到 OKX
DATA_SOURCE_EXCHANGE=okx  # 改这里
DATA_SOURCE_SYMBOLS=BTC/USDT:USDT,ETH/USDT:USDT  # 改格式
```

无需修改代码！

---

## 📁 相关文件

| 文件 | 作用 |
|------|------|
| `.env` | 配置数据源和交易所 |
| `src/core/config.py` | 读取配置 |
| `src/perception/market_data.py` | 通用数据采集器 |
| `main.py` | 主程序（从 config 读取配置） |

---

## 🔄 数据流程

```
.env 配置
    ↓
config.py 读取
    ↓
main.py 初始化
    ↓
CCXTMarketDataCollector (data_source_id)
    ↓
每 3 秒拉取数据
    ↓
缓存到 Redis + 内存
    ↓
main.py 决策循环（每 60 秒）
    ↓
CCXTOrderExecutor (exchange_id) 执行交易
```

---

## 🎓 总结

1. **数据源配置在 .env**：`DATA_SOURCE_EXCHANGE`, `DATA_SOURCE_SYMBOLS`
2. **不需要修改代码**：所有配置都在 `.env` 文件
3. **数据源不需要 Key**：拉公开数据免费
4. **交易才需要 Key**：配置 `BINANCE_API_KEY` 等
5. **切换只需改 .env**：无需重启或修改代码

---

**需要帮助？** 查看示例配置或提交 Issue
