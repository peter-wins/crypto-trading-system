# Exchange Service Module

统一的交易所 API 服务模块,提供集中化的交易所接口访问。

## 架构设计

```
src/exchange/
├── __init__.py              # 公共 API 导出
├── exchange_service.py      # 核心服务类(单例)
├── rate_limiter.py          # Token Bucket 限流器
├── decorators.py            # 可组合装饰器
└── README.md               # 本文档
```

## 核心功能

### 1. 统一 API 接口

`ExchangeService` 提供所有交易所操作的统一入口:

```python
from src.exchange import get_exchange_service

# 获取全局单例
exchange_service = get_exchange_service()

# 市场数据
ticker = await exchange_service.fetch_ticker("BTC/USDT")
ohlcv = await exchange_service.fetch_ohlcv("BTC/USDT", "1h", limit=100)
orderbook = await exchange_service.fetch_order_book("BTC/USDT", limit=20)

# 账户信息
balance = await exchange_service.fetch_balance()
positions = await exchange_service.fetch_positions()

# 订单管理
order = await exchange_service.create_order(
    symbol="BTC/USDT",
    order_type="market",
    side="buy",
    amount=0.01,
    params={"positionSide": "LONG"}
)
await exchange_service.cancel_order(order_id, symbol)
open_orders = await exchange_service.fetch_open_orders("BTC/USDT")

# 杠杆设置
await exchange_service.set_leverage(leverage=10, symbol="BTC/USDT")
```

### 2. 自动限流

基于 Token Bucket 算法,自动限制 API 调用频率:

```python
# 不同交易所有不同的限流规则
EXCHANGE_LIMITS = {
    "binance": 20.0,   # 20 req/s = 1200/minute
    "okx": 300.0,      # 300 req/s
    "bybit": 2.0,      # 2 req/s = 120/minute
    "default": 10.0,
}

# 获取限流统计
stats = exchange_service.get_rate_limiter_stats()
# {
#   "binance": {
#     "total_requests": 1234,
#     "total_waits": 56,
#     "avg_wait_time": 0.15,
#     "current_tokens": 15.3,
#     "recent_rate_per_second": 18.5
#   }
# }
```

### 3. 自动重试

使用指数退避算法自动重试失败的请求:

```python
@api_call(max_retries=3, timeout=10.0)
async def fetch_ticker(self, symbol: str) -> Dict[str, Any]:
    # 自动重试最多 3 次
    # 每次等待时间: 1s, 2s, 4s
    # 超时时间: 10 秒
    ...
```

### 4. 统一错误处理

所有交易所错误自动转换为自定义异常:

```python
try:
    await exchange_service.create_order(...)
except NetworkError:
    # 网络相关错误 (timeout, connection, refused)
    ...
except ExchangeError:
    # 交易所错误 (余额不足, 订单错误, 限流等)
    ...
```

### 5. 完整日志

所有 API 调用自动记录:

```
DEBUG: API call: fetch_ticker(['BTC/USDT'], {}) completed in 0.15s
INFO:  Creating buy market order: BTC/USDT amount=0.01 price=None
DEBUG: Rate limit: waiting 0.05s (tokens: 0.3/40)
```

### 6. 连接池管理

单例模式确保只有一个 exchange 连接:

```python
class ExchangeService:
    _instance: Optional['ExchangeService'] = None

    def __new__(cls):
        # 全局单例,所有模块共享同一连接
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
```

## 使用示例

### 基础用法

```python
from src.exchange import get_exchange_service

async def trade_example():
    service = get_exchange_service()

    # 1. 检查交易所状态
    healthy = await service.health_check()
    if not healthy:
        logger.error("Exchange is not healthy")
        return

    # 2. 获取账户余额
    balance = await service.fetch_balance()
    usdt_balance = balance.get("USDT", {}).get("free", 0)

    # 3. 创建订单
    if usdt_balance > 100:
        order = await service.create_order(
            symbol="BTC/USDT",
            order_type="market",
            side="buy",
            amount=100 / current_price
        )
        logger.info(f"Order created: {order['id']}")
```

### 在 Portfolio Manager 中使用

```python
class PortfolioManager:
    async def _fetch_portfolio_from_exchange(self) -> Portfolio:
        # 使用统一的 ExchangeService
        exchange_service = get_exchange_service()

        # 获取账户余额
        balance = await exchange_service.fetch_balance()

        # 获取持仓列表
        positions_raw = await exchange_service.fetch_positions()

        # 获取未完成订单
        for symbol in symbols:
            orders = await exchange_service.fetch_open_orders(symbol)

        return portfolio
```

## 装饰器说明

### @with_retry

自动重试装饰器:

```python
@with_retry(max_retries=3, backoff_factor=1.0)
async def my_api_call():
    # 失败时自动重试,等待时间: 1s, 2s, 4s
    ...
```

### @with_timeout

超时装饰器:

```python
@with_timeout(seconds=5.0)
async def my_api_call():
    # 超过 5 秒抛出 NetworkError
    ...
```

### @log_api_call

日志装饰器:

```python
@log_api_call
async def my_api_call(symbol: str):
    # 自动记录调用参数、返回值和执行时间
    ...
```

### @handle_exchange_errors

错误处理装饰器:

```python
@handle_exchange_errors
async def my_api_call():
    # 自动将 CCXT 异常转换为自定义异常
    ...
```

### @cached

缓存装饰器:

```python
@cached(ttl=60)
async def fetch_markets(self):
    # 结果缓存 60 秒
    ...
```

### @api_call (组合装饰器)

推荐使用的组合装饰器,包含所有功能:

```python
@api_call(max_retries=3, timeout=10.0, log=True)
async def my_api_call():
    # = @with_retry + @with_timeout + @log_api_call + @handle_exchange_errors
    ...
```

## 限流器详解

### Token Bucket 算法

```python
class RateLimiter:
    def __init__(self, requests_per_second: float = 10.0):
        self.tokens = float(burst_size)  # 令牌桶容量
        self.last_update = time.time()

    async def acquire(self, tokens: int = 1):
        # 1. 根据时间流逝补充令牌
        elapsed = now - self.last_update
        self.tokens = min(burst_size, self.tokens + elapsed * rate)

        # 2. 如果令牌不足,等待
        if self.tokens < tokens:
            wait_time = (tokens - self.tokens) / rate
            await asyncio.sleep(wait_time)

        # 3. 消耗令牌
        self.tokens -= tokens
```

### 限流统计

```python
limiter = rate_limiters.get_limiter("binance")
stats = limiter.get_stats()

# {
#   "total_requests": 1234,        # 总请求数
#   "total_waits": 56,             # 等待次数
#   "avg_wait_time": 0.15,         # 平均等待时间(秒)
#   "current_tokens": 15.3,        # 当前令牌数
#   "recent_rate_per_second": 18.5 # 最近1分钟的请求速率
# }
```

## 配置说明

在 `src/core/config.py` 中配置 API 密钥:

```python
# Binance API
binance_api_key: str = Field(..., env="BINANCE_API_KEY")
binance_api_secret: str = Field(..., env="BINANCE_API_SECRET")
```

在 `.env` 文件中设置:

```bash
BINANCE_API_KEY=your_api_key
BINANCE_API_SECRET=your_api_secret
```

## 设计原则

1. **单一职责**: ExchangeService 只负责 API 调用,不包含业务逻辑
2. **单例模式**: 全局共享一个连接,避免重复初始化
3. **关注点分离**: 限流、重试、日志等通过装饰器解耦
4. **统一接口**: 所有交易所操作都通过同一入口
5. **自动化**: 限流、重试、错误处理全部自动完成

## 与其他模块的关系

```
┌─────────────────────────────────────────────────┐
│              Business Layer                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐     │
│  │Portfolio │  │  Order   │  │  Risk    │     │
│  │ Manager  │  │ Executor │  │ Manager  │     │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘     │
└───────┼─────────────┼─────────────┼────────────┘
        │             │             │
        └─────────────┼─────────────┘
                      ▼
        ┌─────────────────────────────┐
        │    ExchangeService          │
        │  - fetch_balance()          │
        │  - fetch_positions()        │
        │  - create_order()           │
        │  - fetch_ticker()           │
        └──────────────┬──────────────┘
                       │
        ┌──────────────┼──────────────┐
        │              │              │
        ▼              ▼              ▼
   RateLimiter    Decorators    Connection Pool
```

## 最佳实践

1. **总是使用全局单例**:
   ```python
   # ✅ 正确
   service = get_exchange_service()

   # ❌ 错误 - 不要自己创建实例
   service = ExchangeService()
   ```

2. **处理所有异常**:
   ```python
   try:
       await service.create_order(...)
   except NetworkError as e:
       # 网络问题,可以重试
       logger.warning(f"Network error: {e}")
   except ExchangeError as e:
       # 交易所错误,检查参数
       logger.error(f"Exchange error: {e}")
   ```

3. **监控限流统计**:
   ```python
   stats = service.get_rate_limiter_stats()
   if stats["binance"]["total_waits"] > 100:
       logger.warning("Too many rate limit waits")
   ```

4. **在应用退出时关闭连接**:
   ```python
   async def shutdown():
       service = get_exchange_service()
       await service.close()
   ```

## 未来扩展

可能的改进方向:

1. **支持多交易所**: 目前专注于 Binance,未来可以支持多个交易所同时运行
2. **WebSocket 流式数据**: 添加实时市场数据订阅
3. **更智能的限流**: 基于 API weight 的动态限流
4. **故障切换**: 自动切换到备用交易所
5. **性能监控**: 内置 Prometheus 指标

## 故障排除

### 问题: Rate limit exceeded

```
ExchangeError: Rate limit exceeded
```

**解决方案**: 检查是否有多个进程同时调用 API,或降低调用频率。

### 问题: Connection timeout

```
NetworkError: Operation timed out after 10s
```

**解决方案**: 检查网络连接,或增加超时时间。

### 问题: Order not found

```
OrderQueryError: Order not found
```

**解决方案**: 订单可能已经被取消或成交,检查订单状态。

## 总结

`ExchangeService` 是整个交易系统的基础设施层,提供:

- ✅ 统一的 API 接口
- ✅ 自动限流(Token Bucket)
- ✅ 自动重试(指数退避)
- ✅ 超时控制
- ✅ 统一错误处理
- ✅ 完整日志记录
- ✅ 连接池管理
- ✅ 高可用性

使用 `ExchangeService` 可以:
- 避免重复的 exchange 连接管理代码
- 自动处理限流和重试
- 统一错误处理逻辑
- 简化代码,提高可维护性
