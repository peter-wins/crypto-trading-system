# AI自主加密货币交易系统 - 项目概述

## 1. 项目目标

构建一个具备自主认知、决策、执行和学习能力的AI交易系统，使用DeepSeek作为核心决策引擎，实现7x24小时自主交易。

## 2. 核心特性

- **自主感知**: 多源数据实时采集与分析
- **自主决策**: 分层智能决策引擎（战略层+战术层）
- **自主执行**: 智能订单执行与风险控制
- **自主学习**: 持续学习与策略优化

## 3. 技术栈

### 3.1 核心框架
```
- Python 3.11+
- FastAPI (API服务)
- asyncio (异步处理)
- Celery (任务队列)
```

### 3.2 AI模型
```
- DeepSeek (主决策引擎)
- OpenAI Embedding (文本向量化)
- 本地小模型 (特征提取，可选)
```

### 3.3 数据存储
```
- PostgreSQL 15+ (结构化数据)
- Redis 7+ (缓存/短期记忆)
- Qdrant (向量数据库/长期记忆)
- TimescaleDB (时序数据，可选)
```

### 3.4 数据源
```
- CCXT (交易所API)
- CoinGecko/CoinMarketCap (市场数据)
- Etherscan/BSCScan (链上数据，可选)
- Twitter API (情绪数据，可选)
```

### 3.5 监控与部署
```
- Docker + Docker Compose
- Prometheus + Grafana (监控)
- Python logging (日志)
```

## 4. 项目结构

```
crypto-trading-system/
├── src/
│   ├── core/              # 核心组件
│   │   ├── config.py      # 配置管理
│   │   ├── logger.py      # 日志
│   │   └── exceptions.py  # 异常定义
│   │
│   ├── models/            # 数据模型
│   │   ├── market.py      # 市场数据模型
│   │   ├── trade.py       # 交易模型
│   │   └── memory.py      # 记忆模型
│   │
│   ├── perception/        # 感知模块
│   │   ├── market_data.py # 市场数据采集
│   │   ├── onchain.py     # 链上数据
│   │   └── sentiment.py   # 情绪分析
│   │
│   ├── memory/            # 记忆系统
│   │   ├── short_term.py  # 短期记忆(Redis)
│   │   ├── long_term.py   # 长期记忆(Qdrant)
│   │   └── retrieval.py   # 记忆检索
│   │
│   ├── decision/          # 决策引擎
│   │   ├── strategist.py  # 战略决策
│   │   ├── trader.py      # 战术决策
│   │   ├── prompts.py     # Prompt模板
│   │   └── tools.py       # 工具函数
│   │
│   ├── execution/         # 执行模块
│   │   ├── order.py       # 订单执行
│   │   ├── risk.py        # 风险管理
│   │   └── portfolio.py   # 投资组合
│   │
│   ├── learning/          # 学习模块
│   │   ├── performance.py # 绩效评估
│   │   ├── reflection.py  # 自我反思
│   │   └── optimizer.py   # 策略优化
│   │
│   ├── api/               # API服务
│   │   ├── server.py      # FastAPI服务器
│   │   ├── routes/        # 路由
│   │   └── schemas.py     # Pydantic模型
│   │
│   └── agent/             # 主Agent循环
│       └── autonomous_loop.py
│
├── tests/                 # 测试
├── scripts/               # 脚本
├── docs/                  # 文档
│   ├── prd/              # PRD文档
│   ├── api/              # API文档
│   ├── modules/          # 模块开发指南
│   └── database/         # 数据库设计
│
├── config/               # 配置文件
├── docker/               # Docker配置
├── requirements.txt      # Python依赖
└── docker-compose.yml    # 服务编排
```

## 5. 开发原则

### 5.1 模块化设计
- 每个模块必须独立可测试
- 模块间通过明确的接口通信
- 避免循环依赖

### 5.2 接口优先
- 先定义接口（抽象类/Protocol）
- 再实现具体逻辑
- 便于mock和测试

### 5.3 配置外部化
- 所有配置通过环境变量或配置文件
- 不在代码中硬编码
- 支持多环境（dev/test/prod）

### 5.4 错误处理
- 所有外部调用必须有错误处理
- 使用自定义异常
- 详细的错误日志

### 5.5 类型注解
- 所有函数必须有完整类型注解
- 使用Pydantic进行数据验证
- 启用mypy严格模式

## 6. 开发阶段

### Phase 1: 基础设施 (Week 1-2)
- 项目脚手架
- 数据库设计与初始化
- 基础配置和日志系统
- Docker环境搭建

### Phase 2: 感知模块 (Week 2-3)
- 市场数据采集
- 数据清洗与标准化
- 实时数据流处理

### Phase 3: 记忆系统 (Week 3-4)
- Redis短期记忆
- Qdrant向量存储
- 记忆检索与RAG

### Phase 4: 决策引擎 (Week 4-6)
- DeepSeek集成
- Prompt工程
- 工具调用框架
- 决策流程实现

### Phase 5: 执行模块 (Week 6-7)
- 交易所集成
- 订单管理
- 风险控制

### Phase 6: 学习模块 (Week 7-8)
- 绩效追踪
- 反思机制
- 策略优化

### Phase 7: 集成测试 (Week 8-9)
- 模拟交易测试
- 压力测试
- 安全测试

### Phase 8: 实盘部署 (Week 9-10)
- 小额实盘
- 监控告警
- 持续优化

## 7. 文档说明

本PRD采用模块化文档设计，方便AI模型分模块开发：

### 核心文档
- `00-PROJECT-OVERVIEW.md` (本文档) - 项目总览
- `01-DATA-MODELS.md` - 数据模型定义
- `02-API-CONTRACTS.md` - 模块接口契约
- `03-DATABASE-SCHEMA.md` - 数据库设计
- `04-DEVELOPMENT-TASKS.md` - 开发任务清单

### 模块开发指南 (docs/modules/)
每个核心模块都有独立的开发文档：
- `perception-module.md` - 感知模块
- `memory-module.md` - 记忆系统
- `decision-module.md` - 决策引擎
- `execution-module.md` - 执行模块
- `learning-module.md` - 学习模块

### API文档 (docs/api/)
- `rest-api.md` - REST API规范
- `internal-api.md` - 内部接口规范

## 8. 开发注意事项

### 8.1 针对AI模型开发
由于使用Claude Code和Codex进行开发，请注意：

1. **每个任务保持独立**: 提供完整上下文，不依赖其他文件
2. **明确的接口定义**: 模块间通过接口交互
3. **详细的类型注解**: 帮助理解数据结构
4. **完整的示例代码**: 每个模块提供使用示例
5. **清晰的依赖关系**: 明确说明需要导入什么

### 8.2 代码规范
```python
# 命名规范
- 类名: PascalCase (MarketDataCollector)
- 函数/变量: snake_case (get_market_data)
- 常量: UPPER_SNAKE_CASE (MAX_POSITION_SIZE)
- 私有成员: _leading_underscore (_internal_method)

# 文档字符串
- 所有公开函数/类必须有docstring
- 使用Google风格
- 包含参数、返回值、异常说明
```

### 8.3 测试要求
```python
# 每个模块都要有对应测试
src/perception/market_data.py  →  tests/perception/test_market_data.py

# 测试覆盖率要求
- 核心模块: >80%
- 工具函数: >90%
```

## 9. 快速开始

开发者拿到本PRD后：

1. 阅读 `00-PROJECT-OVERVIEW.md` (本文档)
2. 查看 `01-DATA-MODELS.md` 了解数据结构
3. 查看 `02-API-CONTRACTS.md` 了解接口定义
4. 根据 `04-DEVELOPMENT-TASKS.md` 选择任务
5. 参考 `docs/modules/` 中对应的模块指南开发
6. 开发完成后运行测试并更新任务状态

## 10. 关键决策记录

### 10.1 为什么选择DeepSeek？
- 推理能力强
- 支持长上下文
- 成本相对较低
- 支持function calling

### 10.2 为什么采用分层决策？
- 战略层：宏观判断，更新频率低
- 战术层：具体执行，更新频率高
- 分离关注点，降低复杂度

### 10.3 为什么使用Qdrant？
- 开源可自部署
- 性能优秀
- 支持过滤查询
- Python客户端完善

### 10.4 为什么不使用强化学习？
- Phase 1先实现基于LLM的决策
- 强化学习在Phase 2作为增强
- 降低初期复杂度

## 11. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| API限流 | 高 | 请求队列、缓存、多账号轮换 |
| 模型推理慢 | 中 | 异步处理、缓存决策、降级策略 |
| 数据质量差 | 高 | 数据验证、异常检测、多源验证 |
| 黑天鹅事件 | 高 | 熔断机制、仓位限制、人工干预 |
| 资金安全 | 极高 | API只读权限、双重签名、限额控制 |

## 12. 成功指标

### 12.1 技术指标
- 系统可用性: >99%
- 决策延迟: <5秒
- 数据更新延迟: <1秒
- 错误率: <0.1%

### 12.2 交易指标
- 夏普比率: >1.5
- 最大回撤: <15%
- 年化收益率: >30%
- 胜率: >55%

## 13. 联系方式

- 技术问题: 参考各模块文档
- Bug反馈: GitHub Issues
- 文档补充: 直接编辑对应markdown文件
