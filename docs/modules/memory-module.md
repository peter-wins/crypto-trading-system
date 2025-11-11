# 记忆系统开发指南

本文档提供记忆系统的架构设计和开发要点。

## 1. 模块概述

记忆系统是AI Agent的核心组件，负责存储和检索交易经验。采用三层架构：

```
┌─────────────────────────────────────────┐
│  应用层（RAG检索）                       │
│  - 语义检索                              │
│  - 上下文构建                            │
│  - Prompt增强                            │
└─────────────────────────────────────────┘
            ↓                    ↓
┌──────────────────┐   ┌──────────────────┐
│ 短期记忆(Redis)   │   │ 长期记忆(Qdrant) │
│ - 实时上下文      │   │ - 向量搜索       │
│ - 市场状态        │   │ - 经验库         │
│ - 临时缓存        │   │ - 持久化存储     │
└──────────────────┘   └──────────────────┘
```

## 2. 短期记忆设计（Redis）

### 2.1 数据结构设计

**参考**: `docs/prd/03-DATABASE-SCHEMA.md` 第3章

```python
# Key命名规范
market:context:{symbol}         # 市场上下文，TTL 5分钟
trading:context                 # 交易上下文，TTL 1小时
market:prices:{symbol}:{tf}     # 价格队列，TTL 1小时
indicators:{symbol}:{name}      # 指标缓存，TTL 5分钟
```

### 2.2 实现要点

**文件**: `src/memory/short_term.py`

**核心类**:
```python
class RedisShortTermMemory:
    def __init__(self, redis_url: str)
    async def set(key, value, ttl)          # 存储
    async def get(key)                      # 获取
    async def get_market_context(symbol)    # 市场上下文
    async def update_trading_context()      # 交易上下文
```

**关键技术**:
- 使用 `redis.asyncio` 异步客户端
- JSON序列化/反序列化（使用pydantic）
- 自动TTL管理
- Pipeline批量操作提升性能

## 3. 长期记忆设计（Qdrant）

### 3.1 Collection Schema

**参考**: `docs/prd/03-DATABASE-SCHEMA.md` 第4章

```python
Collection: trading_experiences
├── Vectors: 1536维（OpenAI embedding）
├── Distance: Cosine
└── Payload:
    ├── id: 经验ID
    ├── situation: 情况描述（文本）
    ├── decision: 决策内容
    ├── outcome: success/failure
    ├── pnl: 盈亏
    ├── importance_score: 重要性评分
    ├── tags: 标签数组
    └── timestamp: 时间戳
```

### 3.2 实现要点

**文件**: `src/memory/long_term.py`

**核心类**:
```python
class QdrantLongTermMemory:
    def __init__(self, qdrant_url: str, embedding_client)
    async def store_experience(exp: TradingExperience)
    async def search_similar(query: MemoryQuery)
    async def update_experience(exp_id, updates)
```

**关键技术**:
- 文本向量化（使用OpenAI embedding API）
- 混合搜索（向量相似度 + 过滤条件）
- 重要性加权排序
- 批量upsert优化

### 3.3 向量化策略

```python
# 经验向量化格式
situation_template = """
市场: {symbol}
价格: {price}
趋势: {trend}
指标: RSI={rsi}, MACD={macd}
持仓: {position}
决策: {decision}
"""

# 查询向量化格式
query_template = """
当前市场: {symbol}
当前价格: {price}
当前趋势: {trend}
当前指标: RSI={rsi}, MACD={macd}
"""
```

## 4. RAG检索设计

### 4.1 检索流程

```
用户查询
    ↓
1. 文本向量化
    ↓
2. Qdrant向量搜索（Top-K相似经验）
    ↓
3. 应用过滤器（outcome=success, importance>0.7）
    ↓
4. 重排序（相似度 × 重要性 × 时间衰减）
    ↓
5. 获取Redis中的当前上下文
    ↓
6. 组合构建增强Prompt
    ↓
返回给LLM
```

### 4.2 实现要点

**文件**: `src/memory/retrieval.py`

**核心类**:
```python
class RAGMemoryRetrieval:
    def __init__(self, short_term, long_term, llm_client)

    async def retrieve_relevant_context(
        situation: str,
        top_k: int = 5
    ) -> Dict:
        """检索相关上下文"""
        # 1. 向量化查询
        # 2. 搜索相似经验
        # 3. 获取当前上下文
        # 4. 组合返回

    async def build_context_for_llm(
        symbol: str,
        decision_type: str
    ) -> str:
        """构建LLM Prompt上下文"""
        # 格式化为Prompt字符串
```

**关键技术**:
- 语义相似度搜索
- 多条件过滤（outcome、importance、时间范围）
- 时间衰减因子（越近的经验权重越高）
- 上下文窗口管理（控制token数量）

## 5. 记忆更新策略

### 5.1 存储时机

```python
# 何时存储新经验？
1. 交易完成后 → 存储决策和结果
2. 每日收盘后 → 存储日度总结
3. 策略调整后 → 存储调整原因
4. 重大事件后 → 存储市场事件
```

### 5.2 重要性评分

```python
def calculate_importance(experience):
    """计算经验重要性 (0-1)"""
    score = 0.5  # 基础分

    # 盈亏绝对值越大越重要
    if abs(pnl_percentage) > 10:
        score += 0.3
    elif abs(pnl_percentage) > 5:
        score += 0.2

    # 失败经验更重要（学习教训）
    if outcome == "failure":
        score += 0.1

    # 极端市场情况更重要
    if is_black_swan_event:
        score += 0.2

    return min(score, 1.0)
```

### 5.3 记忆清理

```python
# 定期清理策略（避免存储无限增长）
1. 删除importance_score < 0.3的低价值经验
2. 合并相似度>0.95的重复经验
3. 保留最近3个月的所有经验
4. 3个月前只保留importance>0.7的经验
```

## 6. 接口定义

**参考**: `docs/prd/02-API-CONTRACTS.md` 第3章

所有接口都已在API契约文档中定义，实现时严格遵守接口规范。

## 7. 数据一致性

### 7.1 双写策略

```python
# 重要经验同时写入PostgreSQL和Qdrant
async def store_experience(exp):
    # 1. 写入PostgreSQL（结构化存储）
    await db.insert_experience(exp)

    # 2. 生成向量
    embedding = await embedding_client.embed(exp.situation)

    # 3. 写入Qdrant（向量搜索）
    await qdrant.upsert(exp.id, embedding, exp.to_payload())
```

### 7.2 同步检查

定期检查PostgreSQL和Qdrant的数据一致性，修复不一致的记录。

## 8. 性能优化

### 8.1 缓存策略

```python
# 多级缓存
L1: 内存LRU缓存（最近100个查询结果）
L2: Redis缓存（检索结果，TTL 5分钟）
L3: Qdrant向量数据库
```

### 8.2 批量操作

```python
# 批量存储经验
async def batch_store(experiences: List[Experience]):
    # 批量生成embedding
    texts = [exp.situation for exp in experiences]
    embeddings = await embedding_client.batch_embed(texts)

    # 批量写入Qdrant
    points = [PointStruct(...) for exp, emb in zip(experiences, embeddings)]
    await qdrant.upsert(points)
```

## 9. 监控指标

```python
# 关键监控指标
- 检索延迟（P50, P95, P99）
- 检索准确率（用户反馈）
- Redis命中率
- Qdrant集合大小
- 每日新增经验数
- 向量化API调用次数和成本
```

## 10. 测试要点

```python
# tests/memory/test_short_term.py
- 测试Redis连接
- 测试TTL过期
- 测试序列化/反序列化
- 测试并发访问

# tests/memory/test_long_term.py
- 测试向量搜索准确性
- 测试过滤条件
- 测试批量操作
- 测试数据持久化

# tests/memory/test_retrieval.py
- 测试端到端检索流程
- 测试上下文构建
- 测试边界情况（无相关经验）
```

## 11. 开发顺序建议

```
1. 实现短期记忆（RedisShortTermMemory）      - 2-3小时
2. 实现长期记忆（QdrantLongTermMemory）       - 3-4小时
3. 实现RAG检索（RAGMemoryRetrieval）          - 3-4小时
4. 编写单元测试                                - 2-3小时
5. 集成测试和性能优化                          - 2-3小时
```

## 12. 常见问题

**Q: 向量化成本会不会很高？**
A: 使用缓存减少重复向量化。对于相同的situation文本，缓存embedding结果。

**Q: Qdrant集合大小限制？**
A: 定期清理低价值经验。Qdrant可以存储数百万向量，对我们的用例足够。

**Q: 如何保证检索质量？**
A: 1) 精心设计situation描述模板 2) 使用混合搜索（向量+过滤） 3) 重要性加权排序

**Q: Redis故障怎么办？**
A: 短期记忆丢失不影响核心功能。系统会降级到只使用长期记忆。

## 13. 参考资料

- LangChain Memory模块设计
- LlamaIndex的RAG实现
- Qdrant最佳实践文档
- Redis设计模式
