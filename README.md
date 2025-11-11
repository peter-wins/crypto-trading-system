# AI 自主加密货币交易系统

基于大语言模型(LLM)的智能加密货币交易系统，采用分层决策架构。

## 📁 项目结构

```
crypto-trading-system/
├── backend/                    # 后端服务
│   ├── src/                   # Python源代码
│   │   ├── api/              # FastAPI REST API
│   │   ├── core/             # 核心配置和工具
│   │   ├── decision/         # AI决策层
│   │   ├── execution/        # 交易执行
│   │   ├── perception/       # 市场感知
│   │   ├── memory/           # 记忆系统
│   │   └── models/           # 数据模型
│   ├── tests/                # 测试代码
│   ├── main.py               # 主入口
│   ├── requirements.txt      # Python依赖
│   └── README.md             # 后端文档
│
├── frontend/                   # 前端应用 (Next.js)
│   ├── src/                   # React组件和页面
│   ├── public/                # 静态资源
│   ├── package.json           # Node.js依赖
│   └── README.md              # 前端文档
│
├── config/                     # 配置文件
├── docker/                     # Docker配置
├── docs/                       # 项目文档
├── logs/                       # 日志文件
├── scripts/                    # 工具脚本
├── .env                        # 环境变量配置
├── docker-compose.yml          # Docker编排
└── README.md                   # 本文件

```

## 🚀 快速开始

### 方式1: 使用 Docker Compose (推荐)

```bash
# 启动所有服务(数据库 + 后端 + 前端)
docker-compose up -d

# 查看日志
docker-compose logs -f backend
docker-compose logs -f frontend

# 停止所有服务
docker-compose down
```

访问:
- 前端: http://localhost:3000
- 后端API: http://localhost:8000
- API文档: http://localhost:8000/docs

### 方式2: 本地开发

#### 1. 配置环境变量

复制并编辑 `.env` 文件:

```bash
cp .env.example .env
# 编辑 .env，填入你的API密钥
```

必需配置:
```bash
# 交易所API
BINANCE_API_KEY=your_key
BINANCE_API_SECRET=your_secret

# AI模型API
DEEPSEEK_API_KEY=your_key
OPENAI_API_KEY=your_key

# 数据库(本地开发使用docker-compose启动)
DATABASE_URL=postgresql://dev_user:dev_password@localhost:5433/crypto_trading_dev
```

#### 2. 启动基础设施

```bash
# 启动数据库、Redis、Qdrant
docker-compose up -d postgres redis qdrant
```

#### 3. 启动后端

```bash
cd backend
./start.sh

# 或启动API服务器
./start.sh api
```

#### 4. 启动前端

```bash
cd frontend
npm install
npm run dev
```

## 🏗️ 系统架构

### 分层决策架构

```
战略层 (Strategist)
  ↓ (每小时运行)
  市场regime判断、币种筛选、风险参数
  ↓
战术层 (Trader)
  ↓ (每3分钟运行)
  技术分析、信号生成、仓位管理
  ↓
风控层 (Risk Manager)
  ↓
订单执行 (Order Executor)
  ↓
交易所
```

### 技术栈

**后端**:
- Python 3.11+
- DeepSeek Chat (决策引擎)
- OpenAI (Embedding)
- CCXT (交易所连接)
- PostgreSQL + Redis + Qdrant
- FastAPI

**前端**:
- Next.js 14
- React
- TypeScript
- TailwindCSS
- Shadcn/ui

## 📊 核心功能

### AI决策系统
- ✅ 战略层: 宏观市场分析，regime判断
- ✅ 战术层: 技术指标分析，信号生成
- ✅ 支持多空双向交易
- ✅ LLM控制杠杆倍数

### 风控系统
- ✅ 杠杆限制 (BTC/ETH 1-50x, 山寨 1-20x)
- ✅ 仓位占比限制
- ✅ 止损止盈自动设置
- ✅ 日亏损熔断
- ✅ 强平价格监控

### 技术分析
- ✅ RSI, MACD, SMA, Bollinger Bands
- ✅ 多时间周期分析
- ✅ 实时价格监控

### 交易执行
- ✅ Binance USDT永续合约
- ✅ 订单管理和跟踪
- ✅ 持仓同步
- ✅ 止损止盈订单

## 🔧 开发指南

### 后端开发

```bash
cd backend

# 安装依赖
pip install -r requirements.txt

# 运行测试
pytest tests/

# 代码检查
pylint src/
mypy src/
```

详见 [backend/README.md](./backend/README.md)

### 前端开发

```bash
cd frontend

# 安装依赖
npm install

# 开发模式
npm run dev

# 构建
npm run build
```

详见 [frontend/README.md](./frontend/README.md)

## 📝 配置说明

### 提示词风格配置

在 `.env` 中设置:

```bash
PROMPT_STYLE=balanced  # conservative | balanced | aggressive
```

- **conservative**: 保守策略，风险优先，严格止损
- **balanced**: 中性策略，风险收益平衡
- **aggressive**: 激进策略，机会优先，积极进取

### 杠杆限制配置

```bash
MAX_LEVERAGE_MAINSTREAM=50  # BTC/ETH 最大杠杆
MAX_LEVERAGE_ALTCOIN=20     # 其他币种最大杠杆
HIGH_LEVERAGE_WARNING=25    # 高杠杆警告阈值
```

## ⚠️ 风险提示

1. **本系统仅供学习研究使用**
2. **加密货币交易风险极高，可能损失全部本金**
3. **建议先在测试网环境充分测试**
4. **真实交易前请充分了解风险并谨慎评估**
5. **合理设置风控参数，控制杠杆倍数**

## 📄 许可证

MIT License

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📧 联系方式

如有问题，请提交 Issue。
