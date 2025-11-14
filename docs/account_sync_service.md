# 账户同步服务 (Account Sync Service)

## 概述

统一的账户同步服务，解决以下问题：

1. ✅ **精确的平仓价格** - 通过查询成交记录获取真实成交价
2. ✅ **手续费追踪** - 准确记录每笔交易的手续费
3. ✅ **变化检测** - 自动检测手动平仓、止盈止损触发、强平等
4. ✅ **数据一致性** - 保持本地数据库与交易所同步
5. ✅ **实时数据** - 为 API 和前端提供实时账户信息

## 核心功能

### 1. 定期同步
- 默认每 10 秒同步一次账户数据
- 可配置同步间隔
- 自动重试机制

### 2. 变化检测
检测并分类持仓变化：
- `closed` - 持仓完全关闭
- `reduced` - 部分平仓
- `increased` - 加仓
- `liquidated` - 强制平仓

### 3. 精确计算
- 查询成交记录获取真实成交价
- 计算加权平均价格
- 记录手续费
- 识别平仓原因

### 4. 平仓原因识别
- `manual` - 手动平仓（API 或网页操作）
- `stop_loss` - 止损触发
- `take_profit` - 止盈触发
- `liquidation` - 强制平仓
- `system` - 系统自动平仓

## 使用方法

### 1. 在系统启动时初始化

```python
from src.services.account_sync import AccountSyncService

# 在 TradingSystemBuilder 中
async def _setup_account_sync(self):
    """设置账户同步服务"""
    self.account_sync = AccountSyncService(
        exchange_service=self.exchange_service,
        dao=self.dao,
        sync_interval=10  # 10秒同步一次
    )

    # 启动同步服务
    await self.account_sync.start()

    logger.info("✅ 账户同步服务已启动")
```

### 2. 在决策循环中使用

```python
async def run_decision_loop(self):
    """决策循环"""
    while True:
        # 获取最新账户快照（无需重新同步）
        snapshot = await self.account_sync.get_current_snapshot()

        if snapshot:
            logger.info(f"当前余额: {snapshot.total_balance} USDT")
            logger.info(f"持仓数量: {snapshot.position_count}")
            logger.info(f"未实现盈亏: {snapshot.unrealized_pnl}")

        # 执行决策...
        await asyncio.sleep(60)
```

### 3. 订单执行后强制同步

```python
async def execute_trade(self, symbol, side, amount):
    """执行交易"""
    # 下单
    order = await self.order_executor.place_order(...)

    # 立即同步账户（获取最新状态）
    snapshot = await self.account_sync.force_sync()

    return order, snapshot
```

### 4. API 端点使用

```python
from fastapi import APIRouter
from src.services.account_sync import AccountSyncService

router = APIRouter()

@router.get("/account/balance")
async def get_balance(account_sync: AccountSyncService):
    """获取账户余额"""
    snapshot = await account_sync.get_current_snapshot()

    if not snapshot:
        # 如果没有快照，强制同步
        snapshot = await account_sync.force_sync()

    return {
        "total_balance": float(snapshot.total_balance),
        "available_balance": float(snapshot.available_balance),
        "unrealized_pnl": float(snapshot.unrealized_pnl),
        "timestamp": snapshot.timestamp.isoformat()
    }

@router.get("/account/positions")
async def get_positions(account_sync: AccountSyncService):
    """获取持仓列表"""
    snapshot = await account_sync.get_current_snapshot()

    return {
        "positions": [
            {
                "symbol": p.symbol,
                "side": p.side,
                "amount": float(p.amount),
                "entry_price": float(p.entry_price),
                "current_price": float(p.current_price),
                "unrealized_pnl": float(p.unrealized_pnl),
                "pnl_percentage": float(p.unrealized_pnl / (p.amount * p.entry_price) * 100)
            }
            for p in snapshot.positions
        ],
        "timestamp": snapshot.timestamp.isoformat()
    }

@router.get("/account/stats")
async def get_sync_stats(account_sync: AccountSyncService):
    """获取同步服务统计"""
    return account_sync.get_stats()
```

## 数据流程

```
┌─────────────────┐
│  Exchange API   │
│  (Binance)      │
└────────┬────────┘
         │
         │ 每10秒同步
         ▼
┌─────────────────────────┐
│  Account Sync Service   │
│  ├─ fetch balance       │
│  ├─ fetch positions     │
│  ├─ fetch open orders   │
│  └─ fetch trades        │
└────────┬────────────────┘
         │
         │ 检测变化
         ▼
┌─────────────────────────┐
│  Change Detection       │
│  ├─ Position closed     │──┐
│  ├─ Position reduced    │  │
│  ├─ Position increased  │  │
│  └─ Liquidation         │  │
└─────────────────────────┘  │
                              │
         ┌────────────────────┘
         │ 查询成交记录
         ▼
┌─────────────────────────┐
│  Trade Analysis         │
│  ├─ Calculate avg price │
│  ├─ Sum fees            │
│  ├─ Determine reason    │
│  └─ Get precise PnL     │
└────────┬────────────────┘
         │
         │ 保存
         ▼
┌─────────────────────────┐
│  Database (PostgreSQL)  │
│  ├─ positions           │
│  ├─ closed_positions    │
│  └─ trades              │
└────────┬────────────────┘
         │
         │ 提供数据
         ▼
┌─────────────────────────┐
│  Consumers              │
│  ├─ Decision System     │
│  ├─ API Endpoints       │
│  ├─ Frontend Dashboard  │
│  └─ Analytics           │
└─────────────────────────┘
```

## 配置选项

```python
AccountSyncService(
    exchange_service=exchange_service,  # 必需
    dao=dao,                            # 必需
    sync_interval=10,                   # 同步间隔（秒），默认10
)
```

## 性能考虑

### API 调用频率
每次同步会调用以下 API：
- `fetch_balance` - 1次
- `fetch_positions` - 1次
- `fetch_open_orders` - N次（N = 持仓数量）
- `fetch_my_trades` - 仅在检测到变化时调用

### 优化建议
1. **合理设置同步间隔**
   - 高频交易：5-10秒
   - 中长线：30-60秒
   - 持仓监控：10-30秒

2. **批量处理**
   - 当前已使用 `asyncio.gather` 并行获取数据

3. **缓存策略**
   - 使用 `get_current_snapshot()` 获取缓存数据
   - 仅在必要时使用 `force_sync()`

## 数据库扩展

需要在 `TradingDAO.save_closed_position` 方法中添加以下参数：

```python
async def save_closed_position(
    self,
    position: PositionModel,
    exit_order_id: str,
    exit_price: Decimal,
    exit_time: datetime,
    fee: Decimal = Decimal('0'),           # 新增
    close_reason: str = 'unknown'          # 新增
) -> bool:
    """保存已平仓记录"""
    # ...
```

在 `ClosedPositionModel` 中添加字段：

```python
class ClosedPositionModel(Base):
    # ... 现有字段 ...
    fee = Column(Numeric(20, 8), nullable=False, default=0)
    close_reason = Column(String(50), nullable=True)  # manual, stop_loss, take_profit, liquidation
```

## 监控和日志

服务会记录以下关键事件：

- ✅ 同步成功：`账户同步完成 #123 | 余额: 1000.00 USDT | 持仓: 2`
- ⚠️  检测到变化：`检测到 BTC/USDT:USDT 平仓: 数量=0.1 均价=50000 手续费=5.0 原因=stop_loss`
- ❌ 同步失败：`账户同步失败: ConnectionError`

## 集成检查清单

- [ ] 在 `TradingSystemBuilder` 中初始化服务
- [ ] 在系统启动时调用 `start()`
- [ ] 在系统关闭时调用 `stop()`
- [ ] 扩展数据库模型（添加 fee 和 close_reason 字段）
- [ ] 更新 API 端点使用新服务
- [ ] 前端接入实时数据
- [ ] 配置合适的同步间隔
- [ ] 设置监控和告警

## 故障处理

### 同步失败
- 自动重试（下次循环）
- 记录错误日志
- error_count 计数器增加

### 网络问题
- 使用 ExchangeService 的重试机制
- 超时自动恢复

### 数据不一致
- 定期全量同步
- 手动触发 `force_sync()`

## 未来扩展

1. **实时 WebSocket 支持**
   - 监听交易所 WebSocket 事件
   - 减少 API 调用频率

2. **多账户支持**
   - 支持多个交易所账户
   - 聚合显示

3. **性能分析**
   - 记录每次同步的耗时
   - 优化慢查询

4. **告警系统**
   - 余额低于阈值告警
   - 强平风险告警
   - 异常交易告警
