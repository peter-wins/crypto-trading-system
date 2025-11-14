# PerformanceService 使用指南

## 概述

PerformanceService 是一个用于计算、存储和查询交易绩效指标的服务。

### 核心功能

1. **定时计算** - 每天凌晨自动计算前一天的绩效指标并存储
2. **混合查询** - 历史数据从数据库读取，当天数据实时计算
3. **AI格式化** - 将绩效数据格式化为可读文本供AI使用
4. **趋势分析** - 提供绩效趋势数据

## 快速开始

### 1. 初始化服务

```python
from src.services.database import get_db_manager
from src.services.performance_service import PerformanceService

# 获取数据库管理器
db_manager = get_db_manager(config)

# 创建绩效服务
performance_service = PerformanceService(
    db_manager=db_manager,
    exchange_name="binanceusdm"
)

# 启动服务（启动定时任务）
await performance_service.start()
```

### 2. 手动计算绩效

```python
from datetime import date, timedelta

# 计算昨天的绩效
yesterday = date.today() - timedelta(days=1)
result = await performance_service.calculate_and_save_daily_performance(
    target_date=yesterday,
    force=True  # 强制重新计算
)
```

### 3. 查询绩效摘要

```python
# 获取最近7天的绩效摘要
start_date = date.today() - timedelta(days=7)
summary = await performance_service.get_performance_summary(
    start_date=start_date,
    end_date=date.today()
)

print(f"总收益: ${summary['total_return']:.2f}")
print(f"胜率: {summary['win_rate']:.2f}%")
```

### 4. 供AI使用

```python
# 格式化绩效数据供AI决策使用
ai_text = await performance_service.format_for_ai(
    period="weekly",  # daily/weekly/monthly/recent
    include_details=False
)

# ai_text 包含格式化的Markdown文本，可以直接发送给LLM
print(ai_text)
```

输出示例：
```markdown
## 绩效摘要 (weekly)

**收益情况:**
- 总收益: $-756.32 (-16.94%)
- 最大回撤: $-756.32 (-16.94%)
- 夏普比率: -1.29

**交易统计:**
- 总交易次数: 66
- 盈利次数: 36 | 亏损次数: 30
- 胜率: 54.55%
- 平均盈利: $8.84 | 平均亏损: $-9.94
- 盈亏比: 0.95

**绩效评估:**
- ⚠️ 胜率一般
- ❌ 风险调整收益较差
- ❌ 盈亏比较低
```

### 5. 获取绩效趋势

```python
# 获取最近7天的每日绩效
trend = await performance_service.get_recent_performance_trend(days=7)

for day in trend:
    print(f"{day['date']}: 收益${day['return']:.2f}, 胜率{day['win_rate']:.1f}%")
```

## API 参考

### PerformanceService

#### 初始化

```python
PerformanceService(db_manager: DatabaseManager, exchange_name: str = "binanceusdm")
```

#### 方法

##### start()
启动服务，开启定时任务

```python
await performance_service.start()
```

##### stop()
停止服务

```python
await performance_service.stop()
```

##### calculate_and_save_daily_performance()
计算并保存指定日期的绩效指标

```python
result = await performance_service.calculate_and_save_daily_performance(
    target_date: date,  # 目标日期
    force: bool = False  # 是否强制重新计算
) -> Optional[PerformanceMetricsModel]
```

##### get_performance_summary()
获取绩效摘要（推荐使用）

```python
summary = await performance_service.get_performance_summary(
    start_date: Optional[date] = None,  # 开始日期
    end_date: Optional[date] = None,    # 结束日期
    use_cache: bool = True              # 是否使用缓存
) -> Dict[str, Any]
```

返回字典包含：
- `total_return`: 总收益
- `total_return_percentage`: 总收益率
- `sharpe_ratio`: 夏普比率
- `max_drawdown`: 最大回撤
- `win_rate`: 胜率
- `total_trades`: 总交易次数
- `profitable_trades`: 盈利次数
- `losing_trades`: 亏损次数
- `average_profit`: 平均盈利
- `average_loss`: 平均亏损
- `profit_factor`: 盈亏比

##### format_for_ai()
格式化绩效数据供AI使用

```python
text = await performance_service.format_for_ai(
    period: str = "recent",  # daily/weekly/monthly/recent
    include_details: bool = False
) -> str
```

##### get_recent_performance_trend()
获取最近N天的绩效趋势

```python
trend = await performance_service.get_recent_performance_trend(
    days: int = 7
) -> List[Dict[str, Any]]
```

## 集成到Coordinator

如果你有Coordinator统一管理服务，可以这样集成：

```python
class Coordinator:
    def __init__(self, ...):
        self.performance_service = PerformanceService(
            db_manager=self.db_manager,
            exchange_name=self.exchange_name
        )

    async def start(self):
        # 启动绩效服务
        await self.performance_service.start()

    async def stop(self):
        # 停止绩效服务
        await self.performance_service.stop()
```

## 注意事项

1. **定时任务** - 服务会在每天凌晨00:10自动计算前一天的绩效
2. **数据要求** - 至少需要1个快照和1笔已平仓交易才能计算绩效
3. **混合查询** - 查询包含今天的范围时，会实时计算当天数据
4. **强制计算** - 使用 `force=True` 可以覆盖已有的绩效记录

## 测试

运行测试脚本：

```bash
cd /Users/wins/work/crypto-trading-system/backend
python test_performance_service.py
```

## 数据库表

绩效数据存储在 `performance_metrics` 表中，主要字段：

- `start_date`, `end_date`: 时间范围
- `total_return`: 总收益
- `sharpe_ratio`: 夏普比率
- `max_drawdown`: 最大回撤
- `total_trades`: 总交易次数
- `win_rate`: 胜率
- `profit_factor`: 盈亏比
