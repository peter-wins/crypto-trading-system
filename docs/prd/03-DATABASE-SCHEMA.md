# 数据库设计文档

本文档定义系统所有数据库的表结构、索引和关系。

## 1. 数据库概览

系统使用三种数据库：

1. **PostgreSQL**: 结构化数据（交易、订单、绩效）
2. **Redis**: 短期记忆（缓存、实时上下文）
3. **Qdrant**: 向量数据库（长期记忆、经验检索）

## 2. PostgreSQL 表结构

### 2.1 交易所和账户

#### exchanges 表
```sql
CREATE TABLE exchanges (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE,
    api_key_encrypted TEXT NOT NULL,
    api_secret_encrypted TEXT NOT NULL,
    password_encrypted TEXT,
    testnet BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_exchanges_name ON exchanges(name);
CREATE INDEX idx_exchanges_active ON exchanges(is_active);
```

### 2.2 订单表

#### orders 表
```sql
CREATE TABLE orders (
    id VARCHAR(100) PRIMARY KEY,
    client_order_id VARCHAR(100) UNIQUE NOT NULL,
    exchange_id INTEGER REFERENCES exchanges(id),
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL CHECK (side IN ('buy', 'sell')),
    type VARCHAR(20) NOT NULL CHECK (
        type IN ('market', 'limit', 'stop_loss', 'stop_loss_limit',
                 'take_profit', 'take_profit_limit')
    ),
    status VARCHAR(20) NOT NULL CHECK (
        status IN ('pending', 'open', 'partially_filled', 'filled',
                   'canceled', 'rejected', 'expired')
    ),
    price NUMERIC(20, 8),
    amount NUMERIC(20, 8) NOT NULL,
    filled NUMERIC(20, 8) DEFAULT 0,
    remaining NUMERIC(20, 8),
    cost NUMERIC(20, 8) DEFAULT 0,
    average NUMERIC(20, 8),
    fee NUMERIC(20, 8),
    fee_currency VARCHAR(10),

    -- 止损止盈
    stop_price NUMERIC(20, 8),
    take_profit_price NUMERIC(20, 8),
    stop_loss_price NUMERIC(20, 8),

    -- 关联决策
    decision_id VARCHAR(100),

    -- 时间
    timestamp BIGINT NOT NULL,
    datetime TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- 原始数据
    raw_data JSONB
);

CREATE INDEX idx_orders_symbol ON orders(symbol);
CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_orders_datetime ON orders(datetime DESC);
CREATE INDEX idx_orders_exchange ON orders(exchange_id);
CREATE INDEX idx_orders_decision ON orders(decision_id);
```

### 2.3 成交记录表

#### trades 表
```sql
CREATE TABLE trades (
    id VARCHAR(100) PRIMARY KEY,
    order_id VARCHAR(100) REFERENCES orders(id),
    exchange_id INTEGER REFERENCES exchanges(id),
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL CHECK (side IN ('buy', 'sell')),
    price NUMERIC(20, 8) NOT NULL,
    amount NUMERIC(20, 8) NOT NULL,
    cost NUMERIC(20, 8) NOT NULL,
    fee NUMERIC(20, 8),
    fee_currency VARCHAR(10),

    timestamp BIGINT NOT NULL,
    datetime TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    raw_data JSONB
);

CREATE INDEX idx_trades_order ON trades(order_id);
CREATE INDEX idx_trades_symbol ON trades(symbol);
CREATE INDEX idx_trades_datetime ON trades(datetime DESC);
```

### 2.4 持仓表

#### positions 表
```sql
CREATE TABLE positions (
    id SERIAL PRIMARY KEY,
    exchange_id INTEGER REFERENCES exchanges(id),
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL CHECK (side IN ('buy', 'sell')),
    amount NUMERIC(20, 8) NOT NULL,
    entry_price NUMERIC(20, 8) NOT NULL,
    current_price NUMERIC(20, 8) NOT NULL,
    unrealized_pnl NUMERIC(20, 8),
    unrealized_pnl_percentage NUMERIC(10, 4),
    value NUMERIC(20, 8),

    -- 风险控制
    stop_loss NUMERIC(20, 8),
    take_profit NUMERIC(20, 8),

    -- 状态
    is_open BOOLEAN DEFAULT TRUE,

    -- 时间
    opened_at TIMESTAMP NOT NULL,
    closed_at TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(exchange_id, symbol, is_open)
);

CREATE INDEX idx_positions_symbol ON positions(symbol);
CREATE INDEX idx_positions_is_open ON positions(is_open);
CREATE INDEX idx_positions_exchange ON positions(exchange_id);
```

### 2.5 投资组合快照表

#### portfolio_snapshots 表
```sql
CREATE TABLE portfolio_snapshots (
    id SERIAL PRIMARY KEY,
    exchange_id INTEGER REFERENCES exchanges(id),

    -- 总览
    total_value NUMERIC(20, 8) NOT NULL,
    cash NUMERIC(20, 8) NOT NULL,
    positions_value NUMERIC(20, 8),

    -- 绩效
    total_pnl NUMERIC(20, 8),
    daily_pnl NUMERIC(20, 8),
    total_return NUMERIC(10, 4),

    -- 详细持仓
    positions JSONB,

    -- 时间
    snapshot_date DATE NOT NULL,
    timestamp BIGINT NOT NULL,
    datetime TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(exchange_id, snapshot_date)
);

CREATE INDEX idx_portfolio_snapshots_date ON portfolio_snapshots(snapshot_date DESC);
CREATE INDEX idx_portfolio_snapshots_exchange ON portfolio_snapshots(exchange_id);
```

### 2.6 决策记录表

#### decisions 表
```sql
CREATE TABLE decisions (
    id VARCHAR(100) PRIMARY KEY,
    decision_layer VARCHAR(20) NOT NULL CHECK (
        decision_layer IN ('strategic', 'tactical')
    ),

    -- 输入上下文
    input_context JSONB NOT NULL,

    -- 决策过程
    thought_process TEXT NOT NULL,
    tools_used TEXT[],

    -- 输出
    decision TEXT NOT NULL,
    action_taken TEXT,

    -- 元信息
    model_used VARCHAR(50),
    tokens_used INTEGER,
    latency_ms INTEGER,

    -- 时间
    timestamp BIGINT NOT NULL,
    datetime TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_decisions_layer ON decisions(decision_layer);
CREATE INDEX idx_decisions_datetime ON decisions(datetime DESC);
```

### 2.7 交易经验表（补充Qdrant）

#### experiences 表
```sql
CREATE TABLE experiences (
    id VARCHAR(100) PRIMARY KEY,

    -- 情景
    situation TEXT NOT NULL,
    situation_tags TEXT[],

    -- 决策
    decision TEXT NOT NULL,
    decision_reasoning TEXT NOT NULL,
    decision_id VARCHAR(100) REFERENCES decisions(id),

    -- 结果
    outcome VARCHAR(20) NOT NULL CHECK (outcome IN ('success', 'failure')),
    pnl NUMERIC(20, 8),
    pnl_percentage NUMERIC(10, 4),

    -- 反思
    reflection TEXT,
    lessons_learned TEXT[],

    -- 重要性
    importance_score NUMERIC(3, 2) DEFAULT 0.5,

    -- 关联
    related_orders TEXT[],
    symbol VARCHAR(20),

    -- 时间
    timestamp BIGINT NOT NULL,
    datetime TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_experiences_outcome ON experiences(outcome);
CREATE INDEX idx_experiences_importance ON experiences(importance_score DESC);
CREATE INDEX idx_experiences_datetime ON experiences(datetime DESC);
CREATE INDEX idx_experiences_symbol ON experiences(symbol);
CREATE INDEX idx_experiences_tags ON experiences USING GIN(situation_tags);
```

### 2.8 策略配置表

#### strategies 表
```sql
CREATE TABLE strategies (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    version VARCHAR(20) NOT NULL,
    description TEXT,

    -- 策略参数
    config JSONB NOT NULL,

    -- 状态
    is_active BOOLEAN DEFAULT FALSE,

    -- 绩效追踪
    total_trades INTEGER DEFAULT 0,
    win_rate NUMERIC(5, 2),
    total_return NUMERIC(10, 4),

    -- 时间
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    activated_at TIMESTAMP,
    deactivated_at TIMESTAMP,

    -- 更新原因
    reason_for_update TEXT,

    UNIQUE(name, version)
);

CREATE INDEX idx_strategies_active ON strategies(is_active);
CREATE INDEX idx_strategies_name ON strategies(name);
```

### 2.9 绩效指标表

#### performance_metrics 表
```sql
CREATE TABLE performance_metrics (
    id SERIAL PRIMARY KEY,
    strategy_id INTEGER REFERENCES strategies(id),

    -- 时间范围
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,

    -- 收益指标
    total_return NUMERIC(10, 4),
    annualized_return NUMERIC(10, 4),
    daily_returns JSONB,

    -- 风险指标
    volatility NUMERIC(10, 4),
    max_drawdown NUMERIC(10, 4),
    sharpe_ratio NUMERIC(10, 4),
    sortino_ratio NUMERIC(10, 4),
    calmar_ratio NUMERIC(10, 4),

    -- 交易统计
    total_trades INTEGER,
    winning_trades INTEGER,
    losing_trades INTEGER,
    win_rate NUMERIC(5, 2),
    avg_win NUMERIC(20, 8),
    avg_loss NUMERIC(20, 8),
    profit_factor NUMERIC(10, 4),

    -- 其他
    max_consecutive_wins INTEGER,
    max_consecutive_losses INTEGER,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(strategy_id, start_date, end_date)
);

CREATE INDEX idx_performance_metrics_strategy ON performance_metrics(strategy_id);
CREATE INDEX idx_performance_metrics_date_range ON performance_metrics(start_date, end_date);
```

### 2.10 系统事件表

#### system_events 表
```sql
CREATE TABLE system_events (
    id VARCHAR(100) PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL CHECK (
        severity IN ('info', 'warning', 'error', 'critical')
    ),

    -- 事件数据
    data JSONB,

    -- 关联
    related_order_id VARCHAR(100),
    related_symbol VARCHAR(20),

    -- 消息
    message TEXT NOT NULL,
    details TEXT,

    -- 时间
    timestamp BIGINT NOT NULL,
    datetime TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_system_events_type ON system_events(event_type);
CREATE INDEX idx_system_events_severity ON system_events(severity);
CREATE INDEX idx_system_events_datetime ON system_events(datetime DESC);
CREATE INDEX idx_system_events_order ON system_events(related_order_id);
```

## 3. Redis 数据结构

### 3.1 短期记忆 Key设计

```
# 市场上下文
market:context:{symbol}
TTL: 5分钟
Value: JSON序列化的MarketContext

# 交易上下文
trading:context
TTL: 1小时
Value: JSON序列化的TradingContext

# 最近价格
market:prices:{symbol}:{timeframe}
TTL: 1小时
Value: List of prices (最近100个)

# 技术指标缓存
indicators:{symbol}:{indicator_name}:{params}
TTL: 5分钟
Value: JSON序列化的指标值

# 订单簿缓存
market:orderbook:{symbol}
TTL: 30秒
Value: JSON序列化的OrderBook

# Ticker缓存
market:ticker:{symbol}
TTL: 10秒
Value: JSON序列化的Ticker

# API限流
ratelimit:{exchange}:{endpoint}
TTL: 1分钟
Value: 请求计数

# 决策缓存（避免重复决策）
decision:cache:{context_hash}
TTL: 5分钟
Value: JSON序列化的决策结果

# 当前持仓缓存
portfolio:positions
TTL: 1分钟
Value: JSON序列化的Position列表
```

### 3.2 Redis使用示例

```python
# 存储市场上下文
await redis.setex(
    f"market:context:{symbol}",
    300,  # 5分钟
    market_context.json()
)

# 获取市场上下文
data = await redis.get(f"market:context:{symbol}")
if data:
    market_context = MarketContext.parse_raw(data)

# 存储价格列表
await redis.lpush(f"market:prices:{symbol}:1h", str(price))
await redis.ltrim(f"market:prices:{symbol}:1h", 0, 99)  # 保留最近100个
await redis.expire(f"market:prices:{symbol}:1h", 3600)

# 限流检查
count = await redis.incr(f"ratelimit:binance:ticker")
await redis.expire(f"ratelimit:binance:ticker", 60)
if count > 1000:
    raise RateLimitError()
```

## 4. Qdrant Collection设计

### 4.1 Trading Experiences Collection

```python
collection_config = {
    "collection_name": "trading_experiences",
    "vectors_config": {
        "size": 1536,  # OpenAI embedding维度
        "distance": "Cosine"
    }
}

# Payload结构
payload = {
    "id": "exp_123",
    "situation": "BTC price at 45000, RSI oversold...",
    "decision": "Enter long position",
    "decision_reasoning": "...",
    "outcome": "success",
    "pnl": 1250.50,
    "pnl_percentage": 2.5,
    "reflection": "...",
    "lessons_learned": ["Wait for confirmation", ...],
    "tags": ["btc", "oversold", "reversal"],
    "importance_score": 0.85,
    "symbol": "BTC/USDT",
    "timestamp": 1704067200000,
    "datetime": "2024-01-01T00:00:00Z"
}

# 索引配置
payload_indexes = [
    {
        "field_name": "outcome",
        "field_schema": "keyword"
    },
    {
        "field_name": "importance_score",
        "field_schema": "float"
    },
    {
        "field_name": "symbol",
        "field_schema": "keyword"
    },
    {
        "field_name": "tags",
        "field_schema": "keyword"
    }
]
```

### 4.2 查询示例

```python
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue

# 相似度搜索
results = client.search(
    collection_name="trading_experiences",
    query_vector=situation_embedding,
    limit=5,
    query_filter=Filter(
        must=[
            FieldCondition(
                key="outcome",
                match=MatchValue(value="success")
            ),
            FieldCondition(
                key="importance_score",
                range={"gte": 0.7}
            )
        ]
    )
)

# 带标签过滤的搜索
results = client.search(
    collection_name="trading_experiences",
    query_vector=embedding,
    limit=10,
    query_filter=Filter(
        must=[
            FieldCondition(
                key="tags",
                match=MatchValue(value="btc")
            )
        ]
    )
)
```

## 5. 数据库初始化脚本

### 5.1 PostgreSQL初始化

```sql
-- scripts/init_postgres.sql

-- 创建数据库
CREATE DATABASE crypto_trading;

\c crypto_trading;

-- 启用扩展
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- 创建所有表（按上面的DDL）
-- ...

-- 创建触发器：自动更新 updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_orders_updated_at
    BEFORE UPDATE ON orders
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_positions_updated_at
    BEFORE UPDATE ON positions
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_experiences_updated_at
    BEFORE UPDATE ON experiences
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_strategies_updated_at
    BEFORE UPDATE ON strategies
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- 创建视图：当前持仓
CREATE VIEW current_positions AS
SELECT * FROM positions
WHERE is_open = TRUE;

-- 创建视图：今日交易
CREATE VIEW today_trades AS
SELECT * FROM trades
WHERE DATE(datetime) = CURRENT_DATE;

-- 创建函数：计算胜率
CREATE OR REPLACE FUNCTION calculate_win_rate(
    p_start_date DATE,
    p_end_date DATE
) RETURNS NUMERIC AS $$
DECLARE
    total_count INTEGER;
    win_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO total_count
    FROM experiences
    WHERE datetime::DATE BETWEEN p_start_date AND p_end_date;

    SELECT COUNT(*) INTO win_count
    FROM experiences
    WHERE datetime::DATE BETWEEN p_start_date AND p_end_date
      AND outcome = 'success';

    IF total_count = 0 THEN
        RETURN 0;
    END IF;

    RETURN (win_count::NUMERIC / total_count) * 100;
END;
$$ LANGUAGE plpgsql;
```

### 5.2 Python初始化代码

```python
# scripts/init_databases.py

import asyncio
from sqlalchemy import create_engine
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance
import redis.asyncio as redis

async def init_postgres(database_url: str):
    """初始化PostgreSQL"""
    engine = create_engine(database_url)

    # 读取并执行SQL文件
    with open('scripts/init_postgres.sql', 'r') as f:
        sql = f.read()

    with engine.connect() as conn:
        conn.execute(sql)

    print("PostgreSQL initialized")

async def init_redis(redis_url: str):
    """初始化Redis"""
    r = await redis.from_url(redis_url)

    # 清空所有数据（谨慎使用！）
    # await r.flushdb()

    # 测试连接
    await r.ping()
    print("Redis initialized")

    await r.close()

async def init_qdrant(qdrant_url: str):
    """初始化Qdrant"""
    client = QdrantClient(url=qdrant_url)

    # 创建collection
    client.recreate_collection(
        collection_name="trading_experiences",
        vectors_config=VectorParams(
            size=1536,
            distance=Distance.COSINE
        )
    )

    # 创建索引
    client.create_payload_index(
        collection_name="trading_experiences",
        field_name="outcome",
        field_schema="keyword"
    )
    client.create_payload_index(
        collection_name="trading_experiences",
        field_name="importance_score",
        field_schema="float"
    )
    client.create_payload_index(
        collection_name="trading_experiences",
        field_name="symbol",
        field_schema="keyword"
    )

    print("Qdrant initialized")

if __name__ == "__main__":
    asyncio.run(init_postgres("postgresql://user:pass@localhost/crypto_trading"))
    asyncio.run(init_redis("redis://localhost:6379/0"))
    asyncio.run(init_qdrant("http://localhost:6333"))
```

## 6. 数据迁移策略

### 6.1 使用Alembic进行版本管理

```python
# alembic/versions/001_initial_schema.py

from alembic import op
import sqlalchemy as sa

def upgrade():
    op.create_table(
        'exchanges',
        sa.Column('id', sa.Integer, primary_key=True),
        # ...
    )

def downgrade():
    op.drop_table('exchanges')
```

### 6.2 数据备份

```bash
# PostgreSQL备份
pg_dump -U user crypto_trading > backup.sql

# Redis备份
redis-cli --rdb dump.rdb

# Qdrant备份（通过API）
curl -X POST 'http://localhost:6333/collections/trading_experiences/snapshots'
```

## 7. 性能优化建议

### 7.1 PostgreSQL优化

```sql
-- 定期分析表
ANALYZE orders;
ANALYZE trades;

-- 定期清理
VACUUM ANALYZE;

-- 分区表（如果数据量大）
CREATE TABLE trades_2024_01 PARTITION OF trades
FOR VALUES FROM ('2024-01-01') TO ('2024-02-01');
```

### 7.2 Redis优化

```python
# 使用pipeline批量操作
pipe = redis.pipeline()
for key, value in data.items():
    pipe.setex(key, 300, value)
await pipe.execute()

# 使用hash减少key数量
await redis.hset("market:tickers", "BTC/USDT", ticker.json())
```

### 7.3 Qdrant优化

```python
# 批量插入
points = [
    PointStruct(
        id=exp.id,
        vector=exp.embedding,
        payload=exp.dict()
    )
    for exp in experiences
]
client.upsert(collection_name="trading_experiences", points=points)
```

## 8. 监控查询

```sql
-- 今日交易统计
SELECT
    COUNT(*) as total_trades,
    SUM(CASE WHEN side = 'buy' THEN 1 ELSE 0 END) as buy_count,
    SUM(CASE WHEN side = 'sell' THEN 1 ELSE 0 END) as sell_count,
    SUM(cost) as total_volume
FROM trades
WHERE DATE(datetime) = CURRENT_DATE;

-- 当前持仓价值
SELECT
    symbol,
    amount,
    current_price,
    value,
    unrealized_pnl,
    unrealized_pnl_percentage
FROM positions
WHERE is_open = TRUE
ORDER BY value DESC;

-- 最近决策
SELECT
    decision_layer,
    LEFT(decision, 100) as decision_preview,
    datetime
FROM decisions
ORDER BY datetime DESC
LIMIT 10;
```
