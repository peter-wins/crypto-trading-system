# 开发任务清单

本文档按优先级和依赖关系拆分所有开发任务。每个任务都可以独立开发。

## 任务状态说明

- ⬜ 未开始
- 🟡 进行中
- ✅ 已完成
- ⏸️ 暂停/阻塞

## Phase 1: 基础设施 (Week 1-2)

### 1.1 项目脚手架 ⬜

**任务**: 创建项目基础结构和配置

**输入文档**:
- `docs/prd/00-PROJECT-OVERVIEW.md` (项目结构章节)

**输出**:
- 完整的目录结构
- `requirements.txt`
- `pyproject.toml`
- `.env.example`
- `.gitignore`
- `README.md`

**验收标准**:
- [ ] 所有目录按文档创建
- [ ] requirements.txt包含所有必要依赖
- [ ] 可以运行 `pip install -r requirements.txt`

**依赖**: 无

**预计时间**: 2小时

---

### 1.2 核心配置模块 ⬜

**任务**: 实现配置管理

**输入文档**:
- `docs/prd/01-DATA-MODELS.md` (配置模型章节)

**输出**:
- `src/core/config.py`
- `config/config.yaml` (示例配置)

**核心功能**:
```python
class Config:
    def __init__(self):
        # 从环境变量和配置文件加载
        pass

    @property
    def database_url(self) -> str:
        pass

    @property
    def redis_url(self) -> str:
        pass

    def get_exchange_config(self, name: str) -> ExchangeConfig:
        pass

    def get_ai_model_config(self, purpose: str) -> AIModelConfig:
        pass
```

**验收标准**:
- [ ] 支持环境变量覆盖
- [ ] 支持多环境(dev/test/prod)
- [ ] API密钥加密存储
- [ ] 有完整的类型注解

**依赖**: 1.1

**预计时间**: 3小时

---

### 1.3 日志系统 ⬜

**任务**: 实现统一日志系统

**输出**:
- `src/core/logger.py`

**核心功能**:
```python
def get_logger(name: str) -> logging.Logger:
    """获取logger实例"""
    pass

# 使用示例
logger = get_logger(__name__)
logger.info("message")
logger.error("error", exc_info=True)
```

**要求**:
- 支持不同级别（DEBUG/INFO/WARNING/ERROR）
- 支持文件输出和控制台输出
- 结构化日志（JSON格式）
- 包含上下文信息（时间戳、模块名、trace_id）

**验收标准**:
- [ ] 可以输出到文件和控制台
- [ ] 日志格式统一
- [ ] 支持日志轮转

**依赖**: 1.2

**预计时间**: 2小时

---

### 1.4 异常定义 ⬜

**任务**: 定义所有自定义异常

**输出**:
- `src/core/exceptions.py`

**需要定义的异常**:
```python
class TradingSystemError(Exception):
    """基础异常"""

class DataCollectionError(TradingSystemError):
    """数据采集异常"""

class LLMError(TradingSystemError):
    """LLM调用异常"""

class OrderExecutionError(TradingSystemError):
    """订单执行异常"""

class RiskCheckError(TradingSystemError):
    """风险检查异常"""

# ... 更多异常
```

**验收标准**:
- [ ] 所有异常继承自基类
- [ ] 有清晰的docstring
- [ ] 可以携带额外上下文信息

**依赖**: 无

**预计时间**: 1小时

---

### 1.5 数据库初始化 ⬜

**任务**: 创建数据库和表结构

**输入文档**:
- `docs/prd/03-DATABASE-SCHEMA.md`

**输出**:
- `scripts/init_postgres.sql`
- `scripts/init_databases.py`
- Alembic配置

**验收标准**:
- [ ] 运行脚本可以创建所有表
- [ ] 索引全部创建
- [ ] 触发器工作正常
- [ ] Alembic可以管理版本

**依赖**: 1.2

**预计时间**: 4小时

---

### 1.6 Docker环境 ⬜

**任务**: 创建开发和生产环境的Docker配置

**输出**:
- `Dockerfile`
- `docker-compose.yml`
- `docker/` 目录下的配置文件

**服务**:
- PostgreSQL
- Redis
- Qdrant
- Python应用

**验收标准**:
- [ ] `docker-compose up` 可以启动所有服务
- [ ] 数据持久化配置正确
- [ ] 网络配置正确

**依赖**: 1.5

**预计时间**: 3小时

---

## Phase 2: 数据模型实现 (Week 2)

### 2.1 市场数据模型 ⬜

**任务**: 实现市场数据Pydantic模型

**输入文档**:
- `docs/prd/01-DATA-MODELS.md` (第2章)

**输出**:
- `src/models/market.py`

**需要实现的模型**:
- `OHLCVData`
- `OrderBook`
- `OrderBookLevel`
- `Ticker`

**验收标准**:
- [ ] 所有模型有完整字段
- [ ] 有数据验证
- [ ] 有使用示例
- [ ] 通过单元测试

**依赖**: 1.1

**预计时间**: 2小时

---

### 2.2 交易模型 ⬜

**任务**: 实现交易相关模型

**输入文档**:
- `docs/prd/01-DATA-MODELS.md` (第3章)

**输出**:
- `src/models/trade.py`

**需要实现的模型**:
- `Order`
- `Trade`
- `Position`
- 相关Enum类型

**验收标准**:
- [ ] 所有模型完整实现
- [ ] 方法逻辑正确（如update_current_price）
- [ ] 通过单元测试

**依赖**: 1.1

**预计时间**: 3小时

---

### 2.3 组合和记忆模型 ⬜

**任务**: 实现投资组合和记忆相关模型

**输入文档**:
- `docs/prd/01-DATA-MODELS.md` (第4、5章)

**输出**:
- `src/models/portfolio.py`
- `src/models/memory.py`

**验收标准**:
- [ ] Portfolio模型完整
- [ ] MarketContext、TradingContext实现
- [ ] TradingExperience、MemoryQuery实现
- [ ] 通过单元测试

**依赖**: 2.1, 2.2

**预计时间**: 3小时

---

### 2.4 决策和绩效模型 ⬜

**任务**: 实现决策和绩效模型

**输入文档**:
- `docs/prd/01-DATA-MODELS.md` (第6、7章)

**输出**:
- `src/models/decision.py`
- `src/models/performance.py`

**验收标准**:
- [ ] TradingSignal、DecisionRecord实现
- [ ] StrategyConfig实现
- [ ] PerformanceMetrics实现
- [ ] 通过单元测试

**依赖**: 2.2, 2.3

**预计时间**: 2小时

---

## Phase 3: 感知模块 (Week 2-3)

### 3.1 CCXT市场数据采集器 ⬜

**任务**: 实现基于CCXT的市场数据采集

**输入文档**:
- `docs/prd/02-API-CONTRACTS.md` (第2.1章)
- `docs/modules/perception-module.md`

**输出**:
- `src/perception/market_data.py`

**需要实现**:
```python
class CCXTMarketDataCollector:
    async def get_ticker(self, symbol: str) -> Ticker
    async def get_ohlcv(...) -> List[OHLCVData]
    async def get_orderbook(...) -> OrderBook
    async def subscribe_ticker(...)
```

**验收标准**:
- [ ] 实现IMarketDataCollector接口
- [ ] 支持多个交易所
- [ ] 有错误处理和重试
- [ ] 有限流保护
- [ ] 通过集成测试

**依赖**: 2.1

**预计时间**: 6小时

---

### 3.2 技术指标计算器 ⬜

**任务**: 实现技术指标计算

**输入文档**:
- `docs/prd/02-API-CONTRACTS.md` (第2.2章)

**输出**:
- `src/perception/indicators.py`

**需要实现的指标**:
- SMA, EMA
- RSI
- MACD
- Bollinger Bands
- ATR, ADX (可选)

**建议库**: pandas-ta 或 ta-lib

**验收标准**:
- [ ] 实现IIndicatorCalculator接口
- [ ] 所有指标计算正确
- [ ] 有单元测试验证结果

**依赖**: 2.1

**预计时间**: 4小时

---

### 3.3 数据标准化和验证 ⬜

**任务**: 实现数据清洗和验证

**输出**:
- `src/perception/validator.py`

**功能**:
- 数据完整性检查
- 异常值检测
- 数据格式标准化
- 缺失数据处理

**验收标准**:
- [ ] 可以检测异常数据
- [ ] 可以填充缺失值
- [ ] 有完整的测试

**依赖**: 2.1

**预计时间**: 3小时

---

## Phase 4: 记忆系统 (Week 3-4)

### 4.1 Redis短期记忆 ⬜

**任务**: 实现基于Redis的短期记忆

**输入文档**:
- `docs/prd/02-API-CONTRACTS.md` (第3.1章)
- `docs/prd/03-DATABASE-SCHEMA.md` (第3章)

**输出**:
- `src/memory/short_term.py`

**需要实现**:
```python
class RedisShortTermMemory:
    async def set(...)
    async def get(...)
    async def get_market_context(...)
    async def update_market_context(...)
    async def get_trading_context(...)
    async def update_trading_context(...)
```

**验收标准**:
- [ ] 实现IShortTermMemory接口
- [ ] 支持自动序列化/反序列化
- [ ] TTL正确设置
- [ ] 有集成测试

**依赖**: 2.3, 1.5

**预计时间**: 4小时

---

### 4.2 Qdrant长期记忆 ⬜

**任务**: 实现基于Qdrant的长期记忆

**输入文档**:
- `docs/prd/02-API-CONTRACTS.md` (第3.2章)
- `docs/prd/03-DATABASE-SCHEMA.md` (第4章)

**输出**:
- `src/memory/long_term.py`

**需要实现**:
```python
class QdrantLongTermMemory:
    async def store_experience(...)
    async def search_similar_experiences(...)
    async def update_experience(...)
    async def get_experience_by_id(...)
```

**验收标准**:
- [ ] 实现ILongTermMemory接口
- [ ] 向量搜索工作正常
- [ ] 支持过滤查询
- [ ] 有集成测试

**依赖**: 2.3, 1.5

**预计时间**: 5小时

---

### 4.3 RAG记忆检索 ⬜

**任务**: 实现检索增强生成

**输入文档**:
- `docs/prd/02-API-CONTRACTS.md` (第3.3章)

**输出**:
- `src/memory/retrieval.py`

**核心功能**:
```python
class RAGMemoryRetrieval:
    async def retrieve_relevant_context(...)
    async def build_context_for_llm(...)
```

**验收标准**:
- [ ] 可以检索相关经验
- [ ] 可以组合多源上下文
- [ ] Prompt格式化正确
- [ ] 有单元测试

**依赖**: 4.1, 4.2

**预计时间**: 4小时

---

## Phase 5: 决策引擎 (Week 4-6)

### 5.1 LLM客户端 ⬜

**任务**: 实现DeepSeek和OpenAI客户端

**输入文档**:
- `docs/prd/02-API-CONTRACTS.md` (第4.1章)

**输出**:
- `src/decision/llm_client.py`

**需要实现**:
```python
class DeepSeekClient:
    async def chat(...) -> LLMResponse
    async def embed(...) -> List[float]

class OpenAIClient:
    async def chat(...) -> LLMResponse
    async def embed(...) -> List[float]
```

**验收标准**:
- [ ] 实现ILLMClient接口
- [ ] 支持function calling
- [ ] 有重试和错误处理
- [ ] 有token使用统计
- [ ] 有单元测试（使用mock）

**依赖**: 2.4

**预计时间**: 6小时

---

### 5.2 Prompt模板 ⬜

**任务**: 设计和实现所有Prompt模板

**输出**:
- `src/decision/prompts.py`

**需要的Prompt**:
- 战略决策者（Strategist）系统提示
- 战术交易者（Trader）系统提示
- 反思引擎提示
- 工具使用说明

**验收标准**:
- [ ] 所有Prompt清晰明确
- [ ] 支持变量替换
- [ ] 有示例对话
- [ ] 经过测试验证有效

**依赖**: 无

**预计时间**: 4小时

---

### 5.3 决策工具 ⬜

**任务**: 实现LLM可调用的工具

**输入文档**:
- `docs/prd/02-API-CONTRACTS.md` (第7.1章)

**输出**:
- `src/decision/tools.py`

**需要实现的工具**:
- `MarketDataQueryTool`: 查询市场数据
- `TechnicalAnalysisTool`: 技术分析
- `RiskCalculatorTool`: 风险计算
- `MemorySearchTool`: 搜索历史经验
- `BacktestTool`: 简单回测（可选）

**验收标准**:
- [ ] 每个工具实现ITool接口
- [ ] 可以转换为OpenAI function格式
- [ ] 有完整的JSON Schema
- [ ] 有单元测试

**依赖**: 3.1, 3.2, 4.3

**预计时间**: 6小时

---

### 5.4 战略决策器 ⬜

**任务**: 实现战略层决策

**输入文档**:
- `docs/prd/02-API-CONTRACTS.md` (第4.2章)
- `docs/modules/decision-module.md`

**输出**:
- `src/decision/strategist.py`

**核心功能**:
```python
class LLMStrategist:
    async def analyze_market_regime(...)
    async def make_strategic_decision(...)
    async def update_risk_parameters(...)
```

**验收标准**:
- [ ] 实现IStrategist接口
- [ ] 可以分析市场状态
- [ ] 可以制定策略
- [ ] 决策有详细推理
- [ ] 有集成测试

**依赖**: 5.1, 5.2, 5.3, 4.3

**预计时间**: 8小时

---

### 5.5 战术交易器 ⬜

**任务**: 实现战术层决策

**输入文档**:
- `docs/prd/02-API-CONTRACTS.md` (第4.3章)
- `docs/modules/decision-module.md`

**输出**:
- `src/decision/trader.py`

**核心功能**:
```python
class LLMTrader:
    async def generate_trading_signal(...)
    async def calculate_position_size(...)
```

**验收标准**:
- [ ] 实现ITrader接口
- [ ] 可以生成交易信号
- [ ] 可以计算仓位
- [ ] 有完整推理过程
- [ ] 有集成测试

**依赖**: 5.1, 5.2, 5.3, 4.3

**预计时间**: 8小时

---

## Phase 6: 执行模块 (Week 6-7)

### 6.1 订单执行器 ⬜

**任务**: 实现订单执行

**输入文档**:
- `docs/prd/02-API-CONTRACTS.md` (第5.1章)

**输出**:
- `src/execution/order.py`

**核心功能**:
```python
class CCXTOrderExecutor:
    async def create_order(...)
    async def cancel_order(...)
    async def get_order(...)
    async def get_open_orders(...)
```

**验收标准**:
- [ ] 实现IOrderExecutor接口
- [ ] 支持多种订单类型
- [ ] 有完整错误处理
- [ ] 订单状态追踪
- [ ] 有模拟模式用于测试

**依赖**: 2.2

**预计时间**: 6小时

---

### 6.2 风险管理器 ⬜

**任务**: 实现风险控制

**输入文档**:
- `docs/prd/02-API-CONTRACTS.md` (第5.2章)

**输出**:
- `src/execution/risk.py`

**核心功能**:
```python
class StandardRiskManager:
    async def check_order_risk(...)
    async def check_position_risk(...)
    async def check_portfolio_risk(...)
    async def calculate_stop_loss_take_profit(...)
```

**验收标准**:
- [ ] 实现IRiskManager接口
- [ ] 仓位限制检查
- [ ] 止损止盈计算正确
- [ ] 熔断机制工作
- [ ] 有完整单元测试

**依赖**: 2.3, 2.4

**预计时间**: 5小时

---

### 6.3 投资组合管理器 ⬜

**任务**: 实现组合管理

**输入文档**:
- `docs/prd/02-API-CONTRACTS.md` (第5.3章)

**输出**:
- `src/execution/portfolio.py`

**核心功能**:
```python
class PortfolioManager:
    async def get_current_portfolio(...)
    async def update_portfolio(...)
    async def calculate_metrics(...)
```

**验收标准**:
- [ ] 实现IPortfolioManager接口
- [ ] 可以同步交易所状态
- [ ] 绩效计算正确
- [ ] 有数据持久化
- [ ] 有单元测试

**依赖**: 2.3, 6.1

**预计时间**: 6小时

---

## Phase 7: 学习模块 (Week 7-8)

### 7.1 绩效评估器 ⬜

**任务**: 实现绩效评估

**输入文档**:
- `docs/prd/02-API-CONTRACTS.md` (第6.1章)

**输出**:
- `src/learning/performance.py`

**核心功能**:
```python
class PerformanceEvaluator:
    async def evaluate_trade(...)
    async def evaluate_period(...)
    async def compare_with_benchmark(...)
```

**验收标准**:
- [ ] 实现IPerformanceEvaluator接口
- [ ] 计算所有关键指标（夏普、最大回撤等）
- [ ] 可以与基准比较
- [ ] 有单元测试

**依赖**: 2.4, 6.3

**预计时间**: 5小时

---

### 7.2 反思引擎 ⬜

**任务**: 实现自我反思

**输入文档**:
- `docs/prd/02-API-CONTRACTS.md` (第6.2章)

**输出**:
- `src/learning/reflection.py`

**核心功能**:
```python
class LLMReflectionEngine:
    async def reflect_on_trade(...)
    async def reflect_on_period(...)
    async def identify_patterns(...)
```

**验收标准**:
- [ ] 实现IReflectionEngine接口
- [ ] 可以对单笔交易反思
- [ ] 可以识别模式
- [ ] 反思结果有价值
- [ ] 有集成测试

**依赖**: 5.1, 7.1

**预计时间**: 6小时

---

### 7.3 策略优化器 ⬜

**任务**: 实现策略参数优化

**输出**:
- `src/learning/optimizer.py`

**功能**:
- 根据历史表现调整参数
- A/B测试不同策略
- 自动停用表现差的策略

**验收标准**:
- [ ] 可以自动调整参数
- [ ] 有回测验证
- [ ] 有单元测试

**依赖**: 7.1

**预计时间**: 6小时

---

## Phase 8: 主Agent循环 (Week 8)

### 8.1 自主循环实现 ⬜

**任务**: 实现主Agent循环

**输出**:
- `src/agent/autonomous_loop.py`

**核心逻辑**:
```python
class AutonomousAgent:
    async def run(self):
        while True:
            # 1. 感知
            # 2. 检索记忆
            # 3. 决策
            # 4. 执行
            # 5. 学习
            # 6. 存储记忆
            await asyncio.sleep(self.config.loop_interval)
```

**验收标准**:
- [ ] 完整的感知-决策-执行-学习循环
- [ ] 有错误恢复机制
- [ ] 可以优雅停止
- [ ] 有完整日志
- [ ] 有集成测试

**依赖**: 3.1, 4.3, 5.4, 5.5, 6.1, 6.2, 7.2

**预计时间**: 8小时

---

### 8.2 任务调度 ⬜

**任务**: 实现定时任务

**输出**:
- `src/agent/scheduler.py`

**功能**:
- 定期同步数据
- 定期反思
- 定期生成报告
- 定期备份

**工具**: APScheduler 或 Celery

**验收标准**:
- [ ] 所有定时任务正常运行
- [ ] 任务不会重复执行
- [ ] 有任务监控

**依赖**: 8.1

**预计时间**: 4小时

---

## Phase 9: API服务 (Week 8-9)

### 9.1 REST API ⬜

**任务**: 实现Web API

**输出**:
- `src/api/server.py`
- `src/api/routes/` (多个路由文件)
- `src/api/schemas.py`

**端点**:
- GET /portfolio - 获取组合
- GET /positions - 获取持仓
- GET /orders - 获取订单
- GET /performance - 获取绩效
- POST /strategy - 更新策略
- GET /decisions - 获取决策历史

**验收标准**:
- [ ] 所有端点实现
- [ ] 有API文档（Swagger）
- [ ] 有认证和授权
- [ ] 有单元测试

**依赖**: 6.3, 7.1

**预计时间**: 8小时

---

### 9.2 WebSocket实时数据 ⬜

**任务**: 实现WebSocket推送

**输出**:
- `src/api/websocket.py`

**功能**:
- 实时推送价格
- 实时推送交易信号
- 实时推送订单状态

**验收标准**:
- [ ] WebSocket连接稳定
- [ ] 数据推送及时
- [ ] 有重连机制

**依赖**: 9.1

**预计时间**: 4小时

---

## Phase 10: 测试和部署 (Week 9-10)

### 10.1 单元测试覆盖 ⬜

**任务**: 补充单元测试

**目标**:
- 核心模块覆盖率 > 80%
- 工具函数覆盖率 > 90%

**输出**:
- `tests/` 下所有测试文件

**依赖**: 所有开发任务

**预计时间**: 12小时

---

### 10.2 集成测试 ⬜

**任务**: 端到端集成测试

**测试场景**:
- 完整交易流程
- 错误恢复
- 并发处理

**依赖**: 10.1

**预计时间**: 8小时

---

### 10.3 模拟交易测试 ⬜

**任务**: 使用模拟账户测试

**输出**:
- 测试报告
- 性能分析

**验收标准**:
- [ ] 运行至少7天
- [ ] 无严重错误
- [ ] 决策合理

**依赖**: 10.2

**预计时间**: 7天(后台运行)

---

### 10.4 监控和告警 ⬜

**任务**: 实现监控

**输出**:
- Prometheus metrics
- Grafana dashboard
- 告警规则

**监控指标**:
- 系统健康度
- 决策延迟
- 交易成功率
- 资金变化

**依赖**: 8.1

**预计时间**: 6小时

---

### 10.5 部署脚本 ⬜

**任务**: 编写部署文档和脚本

**输出**:
- `deploy/` 目录
- 部署文档

**内容**:
- 服务器配置
- 环境变量设置
- 启动脚本
- 备份脚本

**依赖**: 10.4

**预计时间**: 4小时

---

## 优先级说明

**P0 (必须完成)**: 基础设施、核心模块
**P1 (重要)**: 决策引擎、执行模块
**P2 (可选)**: 优化功能、高级特性

## 如何使用本文档

1. **选择任务**: 根据依赖关系选择未开始的任务
2. **阅读相关文档**: 查看"输入文档"列出的文档
3. **开始开发**: 按照"核心功能"和"验收标准"开发
4. **测试**: 确保通过所有验收标准
5. **更新状态**: 完成后更新任务状态为✅
6. **提交代码**: 创建清晰的commit message

## 注意事项

- 每个任务都应该是独立的pull request
- 开发前先写测试（TDD）
- 代码review后才能合并
- 更新文档如果有变化
