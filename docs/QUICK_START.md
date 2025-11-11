# 快速启动指南

## 前提条件

1. Python 3.11+
2. PostgreSQL (端口 5433)
3. Redis (端口 6379)
4. Qdrant (端口 6333，可选)

## 环境配置

### 1. 最小配置（仅需 DeepSeek API Key）

编辑 `.env` 文件：

```bash
# 必须配置
DEEPSEEK_API_KEY=your_deepseek_api_key_here

# 数据源配置（使用稳定的 Binance）
DATA_SOURCE_EXCHANGE=binance
DATA_SOURCE_SYMBOLS=BTC/USDT,ETH/USDT,SOL/USDT

# 其他保持默认即可
```

### 2. 推荐配置（完整功能）

```bash
# DeepSeek (必须)
DEEPSEEK_API_KEY=your_deepseek_api_key_here

# OpenAI (用于向量嵌入，可选)
OPENAI_API_KEY=your_openai_api_key_here

# 数据源（推荐使用 Binance，最稳定）
DATA_SOURCE_EXCHANGE=binance
DATA_SOURCE_SYMBOLS=BTC/USDT,ETH/USDT,SOL/USDT,MATIC/USDT,AVAX/USDT

# 分层决策架构（推荐启用）
LAYERED_DECISION_ENABLED=true
STRATEGIST_INTERVAL=3600  # 1小时
TRADER_INTERVAL=180       # 3分钟
ENABLE_NEWS=false         # 可选，较慢
```

### 3. 数据源选择

**推荐**: Binance (最稳定，数据质量高)

| 交易所 | 稳定性 | 数据质量 | 推荐度 |
|--------|--------|---------|--------|
| binance | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ✅ 强烈推荐 |
| binanceusdm | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ✅ 推荐 (合约) |
| okx | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⚠️ 可用 |
| bybit | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⚠️ 可用 |
| hyperliquid | ⭐⭐ | ⭐⭐⭐ | ❌ 不推荐 (不稳定) |

**常见问题**：

```
❌ ERROR: Failed to fetch OHLCV for BTC/USDT (exchange=hyperliquid)
```

**解决方案**：
```bash
# 修改 .env
DATA_SOURCE_EXCHANGE=binance
DATA_SOURCE_SYMBOLS=BTC/USDT,ETH/USDT,SOL/USDT
```

## 快速测试

### 1. 测试端到端决策流程

```bash
# 激活虚拟环境
source venv/bin/activate

# 运行完整测试
python test_end_to_end_decision.py
```

**预期输出**：
```
✅ 感知层 → 成功采集市场环境数据
✅ 战略层 → 成功生成市场状态判断
✅ 战术层 → 成功生成交易信号

🎉 端到端决策流程测试完成!
```

### 2. 测试感知层（含新闻）

```bash
python test_perception_with_news.py
```

### 3. 测试集成配置

```bash
python test_layered_integration.py
```

## 运行主系统

### 传统批量决策模式

```bash
# .env 配置
LAYERED_DECISION_ENABLED=false

# 运行
python main.py
```

### 分层决策模式（推荐）

```bash
# .env 配置
LAYERED_DECISION_ENABLED=true
STRATEGIST_INTERVAL=3600
TRADER_INTERVAL=180

# 运行
python main.py
```

系统会自动检测配置并选择运行模式。

## 常见错误及解决

### 错误 1: Decimal 序列化错误

```
TypeError: Object of type Decimal is not JSON serializable
```

**状态**: ✅ 已修复 (2025-11-08)

**修复位置**: `src/decision/strategist.py`

### 错误 2: AttributeError: should_run_strategist

```
AttributeError: 'LayeredDecisionCoordinator' object has no attribute 'should_run_strategist'
```

**状态**: ✅ 已修复 (2025-11-08)

**修复位置**: `src/decision/layered_coordinator.py`

### 错误 3: Hyperliquid API 失败

```
DataCollectionError: Failed to fetch OHLCV for BTC/USDT (exchange=hyperliquid)
```

**解决方案**: 修改 `.env`
```bash
DATA_SOURCE_EXCHANGE=binance
DATA_SOURCE_SYMBOLS=BTC/USDT,ETH/USDT,SOL/USDT
```

### 错误 4: DeepSeek API Key 未配置

```
ValueError: AI model API key must be set
```

**解决方案**: 在 `.env` 中配置
```bash
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxx
```

### 错误 5: Redis 连接失败

```
ConnectionError: Error connecting to Redis
```

**解决方案**: 启动 Redis
```bash
# macOS
brew services start redis

# Linux
sudo systemctl start redis

# Docker
docker run -d -p 6379:6379 redis:alpine
```

### 错误 6: PostgreSQL 连接失败

```
OperationalError: could not connect to server
```

**解决方案**: 检查 PostgreSQL 配置
```bash
# 确认数据库 URL
DATABASE_URL=postgresql://dev_user:dev_password@localhost:5433/crypto_trading_dev

# 启动数据库
docker-compose up -d postgres
```

## 性能监控

### Token 消耗

**分层决策模式**（推荐）：
- 战略层: 24次/天 × 2,000 tokens = 48k tokens/天
- 战术层: 480次/天 × 3,000 tokens = 1.44M tokens/天
- **总计**: ~1.5M tokens/天
- **成本**: $0.30-0.50/天

**传统批量模式**（不推荐）：
- 每分钟: 50,000 tokens
- **总计**: ~72M tokens/天
- **成本**: $10-20/天

**节省**: 95%+ 💰

### 日志级别

```bash
# 开发调试
LOG_LEVEL=DEBUG

# 生产环境
LOG_LEVEL=INFO

# 仅错误
LOG_LEVEL=ERROR
```

## 下一步

1. ✅ 配置 `.env` 文件
2. ✅ 运行测试验证
3. ✅ 启动主系统
4. 📊 监控日志输出
5. 💰 观察 token 消耗
6. 🎯 根据实际情况调整参数

## 参考文档

- [分层决策架构](LAYERED_DECISION.md)
- [提示词优化总结](PROMPT_OPTIMIZATION.md)
- [API 文档](API.md)
- [配置示例](.env.layered_example)

## 获取帮助

遇到问题？

1. 检查日志: `logs/trading_system.log`
2. 运行测试: `python test_*.py`
3. 查看文档: `docs/`
4. 提交 Issue: GitHub Issues

---

**重要提示**：

⚠️ 在生产环境使用前，请务必：
1. 使用测试网验证策略
2. 设置合理的风险参数
3. 监控系统运行状态
4. 定期备份数据库

💡 建议从小资金开始，逐步提高仓位。
