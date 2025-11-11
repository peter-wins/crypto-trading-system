# Crypto Trading System - Backend

AI驱动的加密货币自主交易系统后端

## 目录结构

```
crypto-trading-system/
├── backend/                # 后端服务
│   ├── src/               # 源代码
│   │   ├── api/           # FastAPI REST API
│   │   ├── core/          # 核心配置和工具
│   │   ├── decision/      # AI决策层(战略+战术)
│   │   ├── execution/     # 交易执行和风控
│   │   ├── perception/    # 市场感知和数据采集
│   │   ├── memory/        # 短期和长期记忆
│   │   ├── learning/      # 绩效分析和反思
│   │   ├── database/      # 数据库访问层
│   │   └── models/        # 数据模型
│   ├── tests/             # 单元测试
│   ├── migrations/        # 数据库迁移SQL
│   ├── main.py           # 主入口
│   ├── start.sh          # 启动脚本
│   ├── Dockerfile        # Docker镜像配置
│   ├── requirements.txt  # Python依赖
│   └── setup.py          # 项目安装配置
├── frontend/              # 前端应用 (Next.js)
│   ├── Dockerfile        # 前端生产镜像
│   └── Dockerfile.dev    # 前端开发镜像
├── docs/                  # 📚 项目文档（统一存放）
├── scripts/               # 🔧 工具脚本（统一存放）
├── docker/                # Docker配置文件
├── config/                # 配置文件
├── logs/                  # 日志文件
├── docker-compose.yml    # Docker编排配置
├── docker-compose.dev.yml # 开发环境Docker配置
└── README.md             # 项目主文档
```

## 快速开始

### 1. 安装依赖

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. 配置环境变量

在项目根目录创建 `.env` 文件：

```bash
# Binance API (必需)
BINANCE_API_KEY=your_api_key
BINANCE_API_SECRET=your_api_secret

# LLM API (必需 - 至少配置一个)
DEEPSEEK_API_KEY=your_deepseek_key
QWEN_API_KEY=your_qwen_key

# 数据库 (必需)
DATABASE_URL=postgresql://user:password@localhost:5432/trading_db

# 日志级别 (可选)
LOG_LEVEL=INFO

# 风控配置 (可选)
MAX_DAILY_LOSS=100.0
MAX_POSITION_SIZE=30.0
```

### 3. 初始化数据库

```bash
# 运行数据库迁移（从项目根目录）
cd ../scripts
./run_migration.sh

# 或手动运行
python migrate_db.py
```

### 4. 运行系统

```bash
# 启动交易系统
./start.sh

# 或直接运行
python main.py
```

### 5. 运行 API 服务器 (可选)

```bash
# 启动 API 服务
./start.sh api

# 或使用 uvicorn
uvicorn src.api.server:app --reload --host 0.0.0.0 --port 8000
```

**API文档**:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

**可用API端点**:
- Portfolio: `GET /api/portfolio`, `GET /api/portfolio/positions`
- Market Data: `GET /api/market/{symbol}/ticker`, `GET /api/market/{symbol}/ohlcv`
- Decisions: `GET /api/decisions`, `GET /api/decisions/latest`
- Performance: `GET /api/performance/metrics`, `GET /api/performance/equity-curve`

## 技术栈

- **Python 3.11+**
- **交易所**: Binance Futures (CCXT)
- **AI模型**: DeepSeek Chat / Qwen (决策), OpenAI (Embedding)
- **数据库**: PostgreSQL (主数据库), Redis (缓存), Qdrant (向量数据库)
- **框架**: FastAPI, Pydantic, SQLAlchemy, asyncpg

## 架构特点

### 三层架构

1. **感知层 (Perception)**
   - 宏观经济数据采集 (FRED API)
   - 加密市场数据采集 (Binance API)
   - K线数据管理和技术指标计算
   - 新闻和情绪分析

2. **决策层 (Decision)**
   - **战略层** (Strategist): 宏观市场分析，每小时运行一次
   - **战术层** (Trader): 技术分析和信号生成，每3分钟运行一次
   - 分层决策协调器

3. **执行层 (Execution)**
   - 订单执行和管理
   - 风险控制和仓位管理
   - 投资组合跟踪

### 风控系统

- **杠杆限制**: BTC/ETH (5-50x), 山寨币 (5-20x)
- **止损止盈**: 自动设置和监控
- **仓位控制**: 单币种保证金占比上限 30%
- **日亏损熔断**: 达到阈值自动停止交易
- **强平风险**: 实时监控距离强平价格

### 记忆系统

- **短期记忆**: Redis 缓存最近决策和市场状态
- **长期记忆**: PostgreSQL 存储历史交易和绩效
- **向量检索**: Qdrant 支持相似案例检索

### 学习系统

- **绩效分析**: 计算夏普比率、最大回撤等指标
- **交易反思**: 定期分析交易得失
- **经验积累**: 存储和检索历史相似案例

## 配置说明

### LLM 模型配置

在 `src/core/config.py` 中可以配置：

```python
# 主决策模型 (战略层 + 战术层)
llm_provider: str = "deepseek"  # 或 "qwen"
llm_model: str = "deepseek-chat"

# 提示词风格
prompt_style: str = "balanced"  # conservative / balanced / aggressive
```

### 决策间隔配置

```python
# 战略层运行间隔 (秒)
strategist_interval: int = 3600  # 1小时

# 战术层运行间隔 (秒)
trader_interval: int = 180  # 3分钟
```

### 风控参数配置

```python
# 单币种最大仓位占比 (%)
max_position_size: float = 30.0

# 日最大亏损 (USDT)
max_daily_loss: float = 100.0

# 止损百分比
stop_loss_percentage: float = 2.0

# 止盈百分比
take_profit_percentage: float = 5.0
```

## 开发指南

### 运行测试

```bash
# 运行所有测试
pytest tests/

# 运行特定模块测试
pytest tests/decision/

# 查看测试覆盖率
pytest --cov=src tests/
```

### 代码检查

```bash
# 类型检查
mypy src/

# 代码风格检查
pylint src/

# 格式化代码
black src/
```

### 数据库管理

```bash
# 查看数据库状态
psql $DATABASE_URL -c "SELECT * FROM exchanges;"

# 备份数据库
pg_dump $DATABASE_URL > backup.sql

# 恢复数据库
psql $DATABASE_URL < backup.sql
```

## 项目文档

文档统一存放在项目根目录的 `docs/` 目录：

- [时区处理指南](../docs/TIMEZONE_GUIDE.md) - 时区转换和时间戳处理
- [杠杆修复文档](../docs/LEVERAGE_BUG_FIX.md) - 杠杆倍数解析问题修复
- [数据缺失诊断](../docs/diagnose_missing_close.md) - K线收盘价缺失问题排查
- [更多文档](../docs/) - 查看完整文档列表

## 故障排除

### 常见问题

1. **数据库连接失败**
   ```bash
   # 检查 PostgreSQL 是否运行
   pg_isready

   # 检查连接字符串
   echo $DATABASE_URL
   ```

2. **Binance API 错误**
   ```bash
   # 检查 API 密钥权限
   # 需要开启: 期货交易权限

   # 检查 IP 白名单
   # Binance 后台 -> API 管理 -> IP 限制
   ```

3. **LLM API 调用失败**
   ```bash
   # 检查 API Key
   echo $DEEPSEEK_API_KEY

   # 检查网络连接
   curl https://api.deepseek.com
   ```

4. **K线数据缺失**
   ```bash
   # 检查数据库中的 K线记录
   psql $DATABASE_URL -c "SELECT COUNT(*) FROM klines;"

   # 重新采集数据
   python -c "from src.perception.kline_manager import KlineManager; import asyncio; asyncio.run(KlineManager().collect_klines())"
   ```

## 性能优化

- **并发采集**: 使用 asyncio 并发采集多个币种数据
- **批量插入**: 数据库操作使用批量插入减少往返
- **连接池**: PostgreSQL 和 Redis 使用连接池
- **缓存策略**: 市场数据使用 Redis 缓存，TTL 30秒
- **索引优化**: 数据库表添加适当索引提升查询速度

## 监控和日志

- **日志文件**: `logs/trading_system.log`
- **日志级别**: DEBUG, INFO, WARNING, ERROR
- **结构化日志**: JSON 格式，便于解析和分析
- **异常追踪**: 完整的堆栈跟踪记录

## 贡献指南

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

## 许可证

本项目采用 MIT 许可证

## 联系方式

如有问题或建议，请提交 Issue 或 Pull Request
