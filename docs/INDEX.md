# 文档索引

本文档提供所有项目文档的快速索引。

## 📋 核心PRD文档

### 1. 项目总览
**[00-PROJECT-OVERVIEW.md](prd/00-PROJECT-OVERVIEW.md)**
- 项目目标和核心特性
- 完整技术栈
- 项目结构
- 开发阶段规划
- 成功指标
- **所有开发的起点**

### 2. 数据模型
**[01-DATA-MODELS.md](prd/01-DATA-MODELS.md)**
- 基础数据类型
- 市场数据模型（OHLCV、OrderBook、Ticker）
- 交易模型（Order、Trade、Position）
- 投资组合模型
- 记忆模型（短期记忆、长期记忆）
- 决策模型（TradingSignal、DecisionRecord）
- 性能评估模型
- **开发任何模块前必读**

### 3. 接口契约
**[02-API-CONTRACTS.md](prd/02-API-CONTRACTS.md)**
- 感知模块接口（数据采集、指标计算）
- 记忆系统接口（短期、长期、检索）
- 决策引擎接口（LLM客户端、决策器）
- 执行模块接口（订单、风险、组合）
- 学习模块接口（评估、反思）
- **模块实现的规范**

### 4. 数据库设计
**[03-DATABASE-SCHEMA.md](prd/03-DATABASE-SCHEMA.md)**
- PostgreSQL表结构（15个表）
- Redis数据结构
- Qdrant Collection设计
- 初始化脚本
- 性能优化建议
- **数据库相关开发必读**

### 5. 开发任务
**[04-DEVELOPMENT-TASKS.md](prd/04-DEVELOPMENT-TASKS.md)**
- 10个Phase，60+个任务
- 每个任务包含：
  - 输入文档
  - 输出物
  - 核心功能
  - 验收标准
  - 依赖关系
  - 预计时间
- **选择开发任务的指南**

## 🛠️ 模块开发指南

### 决策模块
**[decision-module.md](modules/decision-module.md)**
- LLM客户端完整实现（DeepSeek、OpenAI）
- Prompt设计和模板
- 工具调用框架（6个工具）
- 战略决策器实现
- 战术交易器实现
- 包含完整代码示例
- **决策模块开发的详细指南**

### 其他模块
- `perception-module.md` - 感知模块
- `memory-module.md` - 记忆系统
- `execution-module.md` - 执行模块
- `learning-module.md` - 学习模块

## 📖 使用指南

### 新手开发者

**第一次接触项目？按这个顺序阅读：**

1. ✅ 阅读主README：`../README.md`
2. ✅ 项目概述：`prd/00-PROJECT-OVERVIEW.md`
3. ✅ 数据模型：`prd/01-DATA-MODELS.md`
4. ✅ 接口契约：`prd/02-API-CONTRACTS.md`
5. ✅ 选择任务：`prd/04-DEVELOPMENT-TASKS.md`

### AI模型（Claude Code/Codex）

**开发特定任务时：**

```
1. 在 04-DEVELOPMENT-TASKS.md 中找到任务
2. 查看任务的"输入文档"列表
3. 阅读相关文档章节
4. 如果有模块指南，阅读modules/下的对应文档
5. 开始实现
6. 检查验收标准
```

### 人类开发者

**开发工作流：**

```
1. 查看任务清单，选择未开始的任务
2. 创建feature分支
3. 阅读相关文档
4. TDD开发（先写测试）
5. 实现功能
6. 运行测试
7. 更新文档（如有变化）
8. 提交PR
```

## 🔍 快速查找

### 我想知道...

**如何定义一个数据模型？**
→ `prd/01-DATA-MODELS.md`

**如何实现一个模块接口？**
→ `prd/02-API-CONTRACTS.md` + `modules/{module}-module.md`

**数据库表结构是什么？**
→ `prd/03-DATABASE-SCHEMA.md`

**下一步应该做什么？**
→ `prd/04-DEVELOPMENT-TASKS.md`

**如何实现LLM调用？**
→ `modules/decision-module.md` 第2节

**如何设计Prompt？**
→ `modules/decision-module.md` 第3节

**如何实现工具调用？**
→ `modules/decision-module.md` 第3.2节

**项目结构是什么？**
→ `prd/00-PROJECT-OVERVIEW.md` 第4节

**使用什么技术栈？**
→ `prd/00-PROJECT-OVERVIEW.md` 第3节

**如何部署？**
→ `prd/04-DEVELOPMENT-TASKS.md` Phase 10

## 📊 文档完成度

### PRD文档
- [x] 00-PROJECT-OVERVIEW.md
- [x] 01-DATA-MODELS.md
- [x] 02-API-CONTRACTS.md
- [x] 03-DATABASE-SCHEMA.md
- [x] 04-DEVELOPMENT-TASKS.md

### 模块指南
- [x] decision-module.md
- [ ] perception-module.md
- [ ] memory-module.md
- [ ] execution-module.md
- [ ] learning-module.md

### API文档
- [ ] rest-api.md
- [ ] internal-api.md

### 其他文档
- [x] README.md
- [x] INDEX.md (本文档)
- [ ] CONTRIBUTING.md
- [ ] DEPLOYMENT.md

## 📝 文档更新指南

### 添加新文档

1. 在对应目录创建markdown文件
2. 在本INDEX.md中添加链接
3. 在主README.md中更新（如需要）

### 更新现有文档

1. 直接编辑对应的markdown文件
2. 提交时说明更新内容
3. 保持文档间的一致性

### 文档规范

- 使用markdown格式
- 清晰的标题层级
- 代码块要指定语言
- 包含使用示例
- 更新时间戳（可选）

## 🎯 关键路径

### 最小可行产品（MVP）开发路径

```
Phase 1: 基础设施
├── 1.1 项目脚手架
├── 1.2 核心配置模块
├── 1.3 日志系统
└── 1.5 数据库初始化

Phase 2: 数据模型
├── 2.1 市场数据模型
├── 2.2 交易模型
└── 2.3 组合和记忆模型

Phase 3: 感知模块
└── 3.1 CCXT市场数据采集器

Phase 4: 记忆系统
├── 4.1 Redis短期记忆
└── 4.2 Qdrant长期记忆

Phase 5: 决策引擎
├── 5.1 LLM客户端
├── 5.2 Prompt模板
├── 5.3 决策工具
└── 5.4 战略决策器

Phase 6: 执行模块
├── 6.1 订单执行器
└── 6.2 风险管理器

Phase 8: 主Agent循环
└── 8.1 自主循环实现
```

## 💡 使用技巧

### 对于AI模型

**上下文优化：**
- 只加载任务相关的文档章节
- 使用文档中的代码示例作为参考
- 关注"验收标准"确保完成质量

**独立开发：**
- 每个任务都包含完整上下文
- 接口定义清晰，无需查看其他实现
- 数据模型都有完整定义

### 对于人类开发者

**高效阅读：**
- 使用INDEX.md快速定位
- 先读概述，再深入细节
- 收藏常用章节

**协作开发：**
- 更新文档与代码同步
- PR中引用相关文档
- 讨论时链接到具体章节

## 🔗 外部资源

### 参考项目
- Alpha Arena
- NOF1.ai

### 技术文档
- [DeepSeek API文档](https://platform.deepseek.com/docs)
- [CCXT文档](https://docs.ccxt.com/)
- [Qdrant文档](https://qdrant.tech/documentation/)
- [FastAPI文档](https://fastapi.tiangolo.com/)

### 学习资源
- LangChain文档（参考Agent设计）
- AutoGPT项目（参考自主循环）

---

**文档更新时间**: 2024-01-01

**维护者**: AI Trading System Team
